# Bare PPO train loop (Stable-Baselines3) on DrivingEnv.
#
#   python train_ppo.py --random-tracks --hard-mix --steps 1500000

# Import libraries.
import argparse  # For reading command line flags.
import os  # For paths / folders / env vars.
import sys  # So we can add src/ onto the import path.

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')  # Headless - no real window during train.

ROOT = os.path.dirname(os.path.abspath(__file__))  # Folder this script lives in.
sys.path.insert(0, os.path.join(ROOT, 'src'))  # Let us import stuff from src/.

from stable_baselines3 import PPO  # The PPO trainer.
from stable_baselines3.common.callbacks import CheckpointCallback  # Saves mid-train checkpoints.
from stable_baselines3.common.env_util import make_vec_env  # Builds a vector of envs.
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv  # Env runners.


# Function to parse args, build envs, train PPO, and save the final model.
def main():
    p = argparse.ArgumentParser(description='Bare PPO for Self-Driving-AI')
    p.add_argument('--steps', type=int, default=750000)
    p.add_argument('--n-envs', type=int, default=8)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--device', default='auto')
    p.add_argument('--run-dir', default=os.path.join(ROOT, 'runs', 'ppo_v3'))
    p.add_argument('--resume', default=None, help='Path to .zip (same obs size only)')
    p.add_argument('--lr', type=float, default=None, help='Fixed LR override')
    p.add_argument('--random-tracks', action='store_true')
    p.add_argument('--map3-prob', type=float, default=0.15)
    p.add_argument(
        '--hard-mix',
        action='store_true',
        help='Bias procedural mix toward medium/hard (chicanes, variable width)',
    )
    args = p.parse_args()

    # If user left the default run dir but turned random tracks on, point at a better folder name.
    if args.random_tracks and args.run_dir.rstrip('\\/').endswith('ppo_v3'):
        args.run_dir = os.path.join(
            ROOT, 'runs', 'ppo_v5_hard' if args.hard_mix else 'ppo_v4_gen'
        )

    os.makedirs(args.run_dir, exist_ok=True)  # Make sure the run folder exists.
    print('Headless train. Watch with watch_ppo.py / watch_gen.py')
    print('Run dir: ' + str(args.run_dir) + '  steps=' + str(args.steps) + '  n_envs=' + str(args.n_envs))
    if args.random_tracks:
        print('Random tracks ON  map3_prob=' + str(args.map3_prob) + '  hard_mix=' + str(args.hard_mix))

    diffs = ('easy', 'medium', 'hard')
    # Prefer clean circuits; hard is narrower / smoother S-bends, not inkblots.
    # hard_mix puts more weight on medium + hard.
    weights = (0.35, 0.40, 0.25) if args.hard_mix else (0.60, 0.30, 0.10)

    # Function to build one DrivingEnv with the flags we picked above.
    def make_env():
        from rl.env import DrivingEnv
        return DrivingEnv(
            random_tracks=args.random_tracks,
            keep_map3_prob=args.map3_prob if args.random_tracks else 0.0,
            track_difficulties=diffs,
            track_difficulty_weights=weights,
        )

    # Subproc is faster for many envs on the fixed map; random tracks stay on DummyVecEnv
    # because pygame surfaces / generation don't love being pickled across processes.
    vec_cls = SubprocVecEnv if (args.n_envs > 1 and not args.random_tracks) else DummyVecEnv
    if args.random_tracks and args.n_envs > 1:
        print('Using DummyVecEnv x' + str(args.n_envs))
    env = make_vec_env(make_env, n_envs=args.n_envs, seed=args.seed, vec_env_cls=vec_cls)

    # Learning rate: fixed override if --lr was passed, else a small schedule for gen / hard,
    # or a flat 2e-4 for short fresh runs on map_3.
    if args.lr is not None:
        lr = args.lr
        lr_schedule = lr
    elif args.hard_mix or args.random_tracks:
        # Function used by SB3: progress_remaining is 1 at start, 0 at end.
        def lr_schedule(progress_remaining):
            # Start at 1e-4, drop to 5e-5 once we're past about half of training.
            return 1e-4 if progress_remaining > 0.45 else 5e-5

        lr = lr_schedule
    else:
        lr = 2e-4
        lr_schedule = lr

    if args.resume:
        print('Resuming from ' + str(args.resume), flush=True)
        model = PPO.load(args.resume, env=env, device=args.device)
        # Make sure the loaded model keeps using the LR schedule we just built.
        model.lr_schedule = lr_schedule if callable(lr_schedule) else (lambda _: float(lr))
        model.tensorboard_log = os.path.join(args.run_dir, 'tb')
    else:
        print('Fresh PPO  obs=19  net=[256,256,128]')
        model = PPO(
            'MlpPolicy',
            env,
            learning_rate=lr,
            n_steps=2048,
            batch_size=512,
            n_epochs=3,
            gamma=0.995,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
            vf_coef=0.5,
            max_grad_norm=0.5,
            policy_kwargs=dict(net_arch=[256, 256, 128]),
            verbose=1,
            seed=args.seed,
            device=args.device,
            tensorboard_log=os.path.join(args.run_dir, 'tb'),
        )

    # Save a checkpoint every ~50k timesteps (divided by n_envs because SB3 counts per-env).
    ckpt = CheckpointCallback(
        save_freq=max(50000 // args.n_envs, 1),
        save_path=os.path.join(args.run_dir, 'ckpt'),
        name_prefix='ppo',
    )

    model.learn(
        total_timesteps=args.steps,
        callback=ckpt,
        progress_bar=True,
        reset_num_timesteps=not bool(args.resume),  # Keep timestep count if we're resuming.
        tb_log_name='PPO_resume' if args.resume else 'PPO',
    )
    out = os.path.join(args.run_dir, 'ppo_final.zip')
    model.save(out)  # Write the finished model.
    print('saved ' + str(out))
    env.close()  # Shut the envs down cleanly.


if __name__ == '__main__':
    main()
