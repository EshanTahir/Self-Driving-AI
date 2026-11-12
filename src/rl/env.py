# Minimal Gymnasium env wrapped around Car + the map border mask.
# Obs  : car.get_data()          (16 or 19 floats depending on car)
# Act  : [throttle, brake, steer] each in [-1, 1]
# Rew  : car.get_reward()
# Done : car is dead, or we hit the time / step limit
#
# Do NOT set SDL_VIDEODRIVER in here -
# train_ppo.py sets dummy for headless train, watch_ppo needs a real display.

# Import libraries.
import gymnasium as gym  # The gym API wrapper.
import numpy as np  # For arrays / random.
import pygame  # Needed to read border pixels into a mask.
from gymnasium import spaces  # For observation / action boxes.

import mapHandler  # Loads the hand-made maps.
from carHandler import Car  # Same car physics as the NEAT sim.

PHYSICS_DT = 1.0 / 60.0  # One physics tick = 1/60th of a second.
ACTION_REPEAT = 4  # Hold the same action for 4 ticks (~15 decisions a second).
DEFAULT_MAX_STEPS = 4800  # ~80s of physics - enough to get past mid-track corners.


# Function to turn a border surface into a simple 0/1 mask.
# White-ish pixels (r >= 250) = driveable, everything else = wall.
def make_border_mask(border_surf):
    rgb = pygame.surfarray.array3d(border_surf)  # Create var containing the RGB array from the surface.
    return (rgb[:, :, 0] >= 250).astype(np.uint8)  # Only uses the red channel to decide driveable pixels.


# Class used to make a Gymnasium driving environment around one Car.
class DrivingEnv(gym.Env):
    metadata = {'render_modes': []}  # No built-in render modes; watch scripts draw themselves.

    def __init__(
        self,
        max_steps=DEFAULT_MAX_STEPS,
        action_repeat=ACTION_REPEAT,
        seed=None,
        map_pack=None,
        allow_reverse=True,
        fixed_spawn_index=0,
        random_tracks=False,
        gen_prob=1.0,
        keep_map3_prob=0.15,
        track_difficulties=('easy', 'medium', 'hard'),
        track_difficulty_weights=(0.25, 0.35, 0.40),
    ):
        super().__init__()
        pygame.init()  # Need pygame for surfaces / masks even when headless.

        self.max_steps = int(max_steps)  # How many physics ticks before we truncate.
        self.action_repeat = int(action_repeat)  # How many ticks one action is held for.
        self.allow_reverse = bool(allow_reverse)  # Whether we can pick reverse / other spawns.
        self.fixed_spawn_index = int(fixed_spawn_index)  # Which spawn to use when not randomizing.
        self.random_tracks = bool(random_tracks)  # If True, sometimes roll a generated track.
        self.gen_prob = float(gen_prob)  # Chance to actually generate (vs keep current pack).
        self.keep_map3_prob = float(keep_map3_prob)  # Chance to keep the hand-made map_3 instead.
        self.track_difficulties = tuple(track_difficulties)  # Which difficulties we can pick from.
        w = np.asarray(track_difficulty_weights, dtype=np.float64)
        self.track_difficulty_weights = (w / w.sum()).tolist()  # Normalize so they sum to 1.

        maps = mapHandler.get_maps()  # Load all hand-made maps.
        self.map3 = maps[0]  # First map is map_3 (the main one we train against).
        if map_pack is None:
            self.map_pack = self.map3  # Default to map_3 if nothing else was passed in.
        else:
            self.map_pack = map_pack  # Caller already picked a map pack for us.
        self.mask = make_border_mask(self.map_pack[1])  # Build the collision mask from the border image.

        # Observation is 19 floats from the car; action is throttle / brake / steer in [-1, 1].
        self.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(19,), dtype=np.float32)
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(3,), dtype=np.float32)

        self.car = None  # Will hold the Car once we reset.
        self.steps = 0  # Physics ticks used this episode.
        self.ep_return = 0.0  # Total reward collected this episode.
        self.rng = np.random.default_rng(seed)  # Our own RNG so episodes can be seeded.
        self.ep_track_seed = None  # Seed of the generated track this episode (or None).
        self.ep_track_diff = None  # Difficulty string for the current track.

    # Function to swap which map pack the env is using, and rebuild the mask.
    def set_map_pack(self, map_pack):
        self.map_pack = map_pack
        self.mask = make_border_mask(map_pack[1])  # New border = new mask.

    # Function to maybe roll a new procedural track for this episode.
    def maybe_roll_track(self):
        if not self.random_tracks:
            return  # Random tracks are off - keep whatever pack we already have.
        # Mostly use generated loops; sometimes keep map_3 so skill on that map doesn't vanish.
        if self.rng.random() < self.keep_map3_prob:
            self.set_map_pack(self.map3)
            self.ep_track_seed = None
            self.ep_track_diff = 'map3'
            return
        if self.rng.random() > self.gen_prob:
            return  # Skip generating this time; stay on the current pack.
        from rl.trackgen import generate_loop_track  # Import here so headless import stays light.

        seed = int(self.rng.integers(0, 2**31 - 1))  # Fresh seed for this track.
        # Pick easy / medium / hard using the weights we were given.
        diff = str(
            self.rng.choice(self.track_difficulties, p=self.track_difficulty_weights)
        )
        # Hard = narrower + bigger canvas; easy = wider roads.
        if diff == 'hard':
            width = int(self.rng.choice([52, 56, 60, 64]))
            size = int(self.rng.choice([1600, 1700, 1800]))
        elif diff == 'medium':
            width = int(self.rng.choice([60, 66, 72, 78]))
            size = int(self.rng.choice([1500, 1600, 1700]))
        else:
            width = int(self.rng.choice([70, 78, 86, 94]))
            size = int(self.rng.choice([1500, 1600, 1700]))
        n_cp = int(self.rng.integers(14, 24))  # How many checkpoints to sprinkle along the loop.
        pack = generate_loop_track(
            seed=seed,
            size=size,
            road_half_width=width,
            n_checkpoints=n_cp,
            difficulty=diff,
        )
        self.set_map_pack(pack)
        self.ep_track_seed = seed
        self.ep_track_diff = diff

    # Function to build the map_data list Car expects for spawning.
    def spawn_map_data(self):
        spawns = self.map_pack[2]  # List of spawn points on this map.
        idx = self.fixed_spawn_index % len(spawns)  # Default spawn index (wraps safely).
        if self.allow_reverse and len(spawns) > 1:
            idx = int(self.rng.integers(0, len(spawns)))  # Pick a random spawn if allowed.
        spawn = spawns[idx]
        # Generated tracks: no reverse (spawn tangent is one-way).
        if self.ep_track_seed is not None:
            reverse = 0.0
        else:
            # Hand-made maps: maybe reverse if allow_reverse is on.
            reverse = float(self.rng.random()) if self.allow_reverse else 0.0
        return [
            self.map_pack[0],  # Real / visual surface.
            self.map_pack[1],  # Border / collision surface.
            spawn,              # Chosen spawn.
            self.map_pack[3],  # Checkpoints.
            reverse,            # Reverse flag (0..1 style, same as old NEAT).
        ]

    # Function to grab the current observation from the car.
    def get_obs(self):
        data = self.car.get_data()  # Same sensor bundle the NEAT nets used.
        return np.asarray(data, dtype=np.float32)

    # Function to reset the env and spawn a fresh car.
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self.rng = np.random.default_rng(seed)  # Reseed our RNG if gym asked us to.

        self.maybe_roll_track()  # Maybe swap to a new generated track.
        map_data = self.spawn_map_data()  # Build spawn info for Car.
        self.car = Car(0, map_data, renderer=None, sprite_config='BlueCar.png')
        self.car.radars.clear()  # Wipe any leftover radar hits.
        # Shoot radars from -55 to +55 degrees in steps of 10, same as training expects.
        for d in range(-55, 56, 10):
            self.car.check_radar(d, self.mask)

        self.steps = 0  # Reset step counter.
        self.ep_return = 0.0  # Reset episode return.
        return self.get_obs(), {
            'track_seed': self.ep_track_seed,
            'track_diff': self.ep_track_diff,
        }

    # Function to take one env step (may run several physics ticks via action_repeat).
    def step(self, action):
        action = np.asarray(action, dtype=np.float32).reshape(3)  # Force shape (3,).
        throttle, brake, steer = float(action[0]), float(action[1]), float(action[2])

        reward = 0.0
        was_alive = self.car.get_alive()  # Remember if we were alive before this step.
        # Hold the same controls for action_repeat ticks, or until the car dies.
        for _ in range(self.action_repeat):
            if not self.car.get_alive():
                break  # Breaks / exits out of the for loop - car already dead.
            self.car.apply_continuous(throttle, brake, steer)  # Feed continuous controls.
            self.car.update(self.mask, [0, 0], PHYSICS_DT)  # Advance physics one tick.
            reward += self.car.get_reward()  # Add this tick's reward.
            self.steps += 1

        # Extra crash penalty if we just died this step (worse if we were going fast).
        if was_alive and not self.car.get_alive():
            spd = float(self.car.speed)
            reward -= 25.0 + 55.0 * min(spd / max(self.car.max_speed, 1.0), 1.0)

        self.ep_return += reward  # Keep a running total for logging.
        terminated = not self.car.get_alive()  # Dead = episode ended for real.
        truncated = self.steps >= self.max_steps  # Hit the time limit = truncated.

        info = {
            'ep_return': self.ep_return,
            'checkpoints': self.car.checkpoints_completed,
            'speed': self.car.speed,
            'laps': self.car.laps,
        }
        return self.get_obs(), float(reward), bool(terminated), bool(truncated), info
