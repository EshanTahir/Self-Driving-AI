# Bare PPO train loop (Stable-Baselines3) on DrivingEnv.
#
#   python train_ppo.py
#   python train_ppo.py --n-envs 8 --steps 1000000

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
    args = p.parse_args()

    os.makedirs(args.run_dir, exist_ok=True)  # Make sure the run folder exists.
    print('Headless train. Watch with watch_ppo.py')
    print('Run dir: ' + str(args.run_dir) + '  steps=' + str(args.steps) + '  n_envs=' + str(args.n_envs))

    # Function to build one DrivingEnv on the hand-made map.
    def make_env():
        from rl.env import DrivingEnv
        return DrivingEnv()

    # Subproc is faster for many envs on the fixed map.
    vec_cls = SubprocVecEnv if args.n_envs > 1 else DummyVecEnv
    env = make_vec_env(make_env, n_envs=args.n_envs, seed=args.seed, vec_env_cls=vec_cls)

    lr = args.lr if args.lr is not None else 2e-4

    if args.resume:
        print('Resuming from ' + str(args.resume), flush=True)
        model = PPO.load(args.resume, env=env, device=args.device)
        model.lr_schedule = lambda _: float(lr)
        model.tensorboard_log = os.path.join(args.run_dir, 'tb')
    else:
        print('Fresh PPO  obs=19  net=[256,256,128]')
        model = PPO(
            'MlpPolicy',
            env,
            learning_rate=lr,
            n_steps=2048,
            batch_size=256,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
            vf_coef=0.5,
            max_grad_norm=0.5,
            policy_kwargs=dict(net_arch=[256, 256, 128]),
            tensorboard_log=os.path.join(args.run_dir, 'tb'),
            device=args.device,
            seed=args.seed,
            verbose=1,
        )

    ckpt = CheckpointCallback(
        save_freq=max(50_000 // max(args.n_envs, 1), 1),
        save_path=os.path.join(args.run_dir, 'checkpoints'),
        name_prefix='ppo',
    )
    model.learn(total_timesteps=args.steps, callback=ckpt, progress_bar=True)
    out = os.path.join(args.run_dir, 'ppo_final.zip')
    model.save(out)
    print('Saved ' + out)


if __name__ == '__main__':
    main()
