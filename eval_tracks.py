# Zero-shot eval: run a trained PPO policy on procedural B/W loop tracks.
#
#   python eval_tracks.py
#   python eval_tracks.py --n 12 --model runs/ppo_v3/ppo_final.zip
#   python eval_tracks.py --baseline   # also score map_3 for comparison

# Import libraries.
import argparse  # For reading command line flags.
import os  # For paths / folders / env vars.
import statistics  # For mean / summary numbers at the end.
import sys  # So we can add src/ onto the import path / exit.

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')  # Headless - no window needed for eval.

ROOT = os.path.dirname(os.path.abspath(__file__))  # Folder this script lives in.
sys.path.insert(0, os.path.join(ROOT, 'src'))  # Let us import stuff from src/.


# Function to find the newest ppo_final.zip under runs/.
def find_model():
    import glob

    finals = glob.glob(os.path.join(ROOT, 'runs', '**', 'ppo_final.zip'), recursive=True)
    if finals:
        finals.sort(key=os.path.getmtime, reverse=True)  # Newest first.
        return finals[0]
    return None


# Function to shrink / pad an observation so it matches the model's expected size.
# Older checkpoints may expect 16 floats; newer ones expect 19.
def fit_obs(obs, n):
    import numpy as np

    obs = np.asarray(obs, dtype=np.float32).reshape(-1)
    if obs.shape[0] == n:
        return obs  # Already the right size.
    if obs.shape[0] > n:
        return obs[:n]  # Too long - just take the first n values.
    out = np.zeros(n, dtype=np.float32)
    out[: obs.shape[0]] = obs  # Too short - pad the rest with zeros.
    return out


# Function to run one full episode and return the final info dict.
def run_episode(model, env, seed, obs_n):
    obs, _ = env.reset(seed=seed)
    done = False
    while not done:
        action, _ = model.predict(fit_obs(obs, obs_n), deterministic=True)  # No exploration.
        obs, _r, term, trunc, info = env.step(action)
        done = term or trunc  # Dead or hit the step limit.
    return info


# Function to eval a model on generated tracks (and optionally map_3).
def main():
    p = argparse.ArgumentParser(description='Eval PPO on generated B/W tracks')
    p.add_argument('--model', default=None)
    p.add_argument('--n', type=int, default=10, help='Number of generated tracks')
    p.add_argument('--seed0', type=int, default=100)
    p.add_argument('--max-steps', type=int, default=3000)
    p.add_argument('--baseline', action='store_true', help='Also eval on map_3')
    p.add_argument('--save-previews', action='store_true', help='Write PNG previews')
    p.add_argument('--width', type=int, default=70, help='Road half-width in px')
    args = p.parse_args()

    model_path = args.model or find_model()
    if not model_path or not os.path.isfile(model_path):
        print('No model found. Train first or pass --model path.zip')
        sys.exit(1)

    import pygame
    from stable_baselines3 import PPO

    import mapHandler
    from rl.env import DrivingEnv
    from rl.trackgen import generate_loop_track, save_track_preview

    pygame.init()  # Need pygame for surfaces even headless.
    print('Model: ' + str(model_path))
    model = PPO.load(model_path, device='cpu')
    obs_n = int(model.observation_space.shape[0])  # How many floats this checkpoint expects.
    print('Model obs dim: ' + str(obs_n))

    preview_dir = os.path.join(ROOT, 'runs', 'eval_tracks')
    if args.save_previews:
        os.makedirs(preview_dir, exist_ok=True)  # Folder for optional PNG previews.

    rows = []  # Kept for optional future table use / baseline summary.

    # Optional: also run a few episodes on the hand-made map_3 for comparison.
    if args.baseline:
        print("\n--- map_3 baseline (3 eps) ---")
        env = DrivingEnv(max_steps=args.max_steps, allow_reverse=False)
        base = []
        for i in range(3):
            info = run_episode(model, env, seed=i, obs_n=obs_n)
            base.append(info)
            print(
                '  map3 ep' + str(i) + ': cps=' + '{:3d}'.format(info['checkpoints'])
                + '  ret=' + '{:8.1f}'.format(info['ep_return'])
                + '  spd=' + '{:6.1f}'.format(info['speed'])
            )
        rows.append(
            (
                'map_3',
                statistics.mean(x['checkpoints'] for x in base),
                statistics.mean(x['ep_return'] for x in base),
            )
        )

    print("\n--- " + str(args.n) + " generated loops (half-width=" + str(args.width) + ") ---")
    cps_list, ret_list, alive_hits = [], [], 0
    for i in range(args.n):
        seed = args.seed0 + i  # Walk seeds so each track is different but reproducible.
        pack = generate_loop_track(seed=seed, road_half_width=args.width)
        if args.save_previews:
            save_track_preview(pack, os.path.join(preview_dir, 'track_' + str(seed) + '.png'))

        # Fresh env per track so the map pack is locked to this generated loop.
        env = DrivingEnv(
            max_steps=args.max_steps,
            map_pack=pack,
            allow_reverse=False,
            fixed_spawn_index=0,
        )
        info = run_episode(model, env, seed=seed, obs_n=obs_n)
        cps_list.append(info['checkpoints'])
        ret_list.append(info['ep_return'])
        # "alive-ish" = hit at least 3 checkpoints before death / timeout.
        if info['checkpoints'] >= 3:
            alive_hits += 1
        print(
            '  gen seed=' + '{:4d}'.format(seed) + ': cps=' + '{:3d}'.format(info['checkpoints'])
            + '  ret=' + '{:8.1f}'.format(info['ep_return'])
            + '  spd=' + '{:6.1f}'.format(info['speed'])
            + '  n_cp=' + str(len(pack[3]))
        )

    # Print a short summary at the end.
    print("\n=== summary ===")
    print('generated tracks : ' + str(args.n))
    print('mean checkpoints : ' + '{:.2f}'.format(statistics.mean(cps_list)) + '  (max ' + str(max(cps_list)) + ')')
    print('mean return      : ' + '{:.1f}'.format(statistics.mean(ret_list)))
    print('>=3 CP episodes  : ' + str(alive_hits) + '/' + str(args.n))
    if args.save_previews:
        print('previews         : ' + str(preview_dir))
    print('Done. Zero-shot on alien loops - low CP counts mean map_3 overfitting.')


if __name__ == '__main__':
    main()
