# Self-Driving-AI

Self-driving car simulation in 2D, trained two ways:

- **NEAT** — evolve a population of feedforward nets that drive the track
- **PPO** — train a single policy with Stable-Baselines3 on the same car / physics

Cars sense the track with radar-style inputs, output throttle / brake / steering, and get scored for progress. The vehicle physics (drag, lateral friction / slip, steering) and OpenGL rendering (stacked sprites, skids, optional x-ray / computer-vision view) are shared by both training paths.

## Setup

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
```

## NEAT

Evolve a population in the OpenGL viewer:

```bash
python main.py
```

- `main.py` — adds `src/` to the path, boots NEAT
- `config-feedforward.txt` — population size, net I/O, speciation, etc.
- Toggle **Computer Vision** for x-ray radar / checkpoints; **Draw All** shows every alive car in real view (best keeps wheels / skids / radar; others are stacked body only)
- **Skip Gen** button, or press `Space` / `N` — generations also auto-skip when cars never move (~4s), fitness stalls (~7s), survivors are stuck, or a hard ~30s cap hits

## PPO

Same car and maps, wrapped as a Gymnasium env for Stable-Baselines3:

```bash
# Train (headless)
python train_ppo.py
python train_ppo.py --n-envs 8 --steps 1000000

# Watch a trained policy in the OpenGL viewer
python watch_ppo.py

# Procedural Fourier loop tracks
python train_ppo.py --random-tracks
python eval_tracks.py
python watch_gen.py
```

| Piece | Role |
|-------|------|
| `train_ppo.py` | SB3 PPO entrypoint (save / resume under `runs/`) |
| `watch_ppo.py` | OpenGL viewer for a trained checkpoint |
| `src/rl/env.py` | Gymnasium wrapper around `Car` (NEAT left alone) |
| `src/rl/trackgen.py` | Procedural B/W loop tracks |
| `eval_tracks.py` | Zero-shot eval on generated tracks |
| `watch_gen.py` | Watch a policy on generated tracks |

NEAT and PPO share `src/carHandler.py`, the OpenGL renderer, and map 3 — only the learning loop differs.

## Layout

```
src/          simulation + rl env
res/images/   map 3 + UI art
res/cars/     BlueCar (active)
res/fonts/    Pixelar.ttf
runs/         PPO checkpoints / logs (gitignored)
misc/         local-only tools, old maps, extra cars (gitignored)
```

## Stack

Python · Pygame · ModernGL · NEAT-Python · Gymnasium · Stable-Baselines3 · NumPy
