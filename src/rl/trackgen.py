# Procedural loop tracks for PPO train / eval.
# Smooth Fourier-style centerlines (not scribble blobs). Returns:
#   [real_surface, border_surface, spawn_points, checkpoints]
#
# difficulty:
#   easy - wide, gentle oval-ish
#   medium - tighter, more shape, still smooth
#   hard - narrower + one mild S-bend, still driveable

# Import libraries.
import math  # For sin / cos / atan2 when building the loop.

import numpy as np  # For arrays and RNG.
import pygame  # Used to draw the road onto surfaces.


# Function to smooth a closed ring of values a few times.
# Each pass averages each point with its left and right neighbors.
def smooth_closed(values, passes=4):
    out = np.asarray(values, dtype=np.float64)
    for _ in range(passes):
        out = (np.roll(out, 1) + out + np.roll(out, -1)) / 3.0
    return out


# Function to bend a circle into a nicer track shape with a few sine waves.
# Low-frequency only - looks like a real circuit, not noise.
def fourier_radius(ts, rng, base_r, difficulty):
    r = np.full_like(ts, base_r, dtype=np.float64)  # Start as a plain circle of radius base_r.
    # Harder difficulties get more / bigger waves so the shape is less oval.
    if difficulty == 'easy':
        amps = [0.08, 0.04]
    elif difficulty == 'medium':
        amps = [0.14, 0.07, 0.03]
    else:
        amps = [0.18, 0.10, 0.04]
    for k, a in enumerate(amps, start=1):
        amp = base_r * a * rng.uniform(0.6, 1.0)  # Scale the wave a bit randomly.
        phase = rng.uniform(0, 2 * math.pi)  # Random starting phase so tracks differ.
        r += amp * np.sin(k * ts + phase)  # Add this harmonic onto the radius.
    return smooth_closed(r, passes=2)  # Soften so we don't get sharp kinks.


# Function to generate one closed loop track and return a map pack.
# map pack layout matches the hand-made maps: real, border, spawns, checkpoints.
def generate_loop_track(
    seed=0,
    size=1600,
    road_half_width=70,
    n_checkpoints=18,
    n_samples=720,
    difficulty='easy',
):
    rng = np.random.default_rng(seed)  # Seeded RNG so the same seed always makes the same track.
    size = int(size)
    cx = cy = size * 0.5  # Center of the square canvas.
    difficulty = (difficulty or 'easy').lower()
    n_samples = max(360, int(n_samples))  # Don't go below 360 sample points on the loop.

    # Pick base radius, stretch, road width, and whether to add a mild S-bend.
    if difficulty == 'hard':
        base_r = size * rng.uniform(0.28, 0.33)
        stretch_x = rng.uniform(0.92, 1.12)
        stretch_y = rng.uniform(0.92, 1.12)
        # If caller passed a wide default, roll a narrower hard width instead.
        road_half_width = int(rng.integers(56, 70)) if road_half_width >= 70 else int(road_half_width)
        road_half_width = max(52, road_half_width)  # Never go thinner than 52.
        do_s_bend = rng.random() < 0.35  # Sometimes add a small S-bend.
    elif difficulty == 'medium':
        base_r = size * rng.uniform(0.29, 0.34)
        stretch_x = rng.uniform(0.94, 1.1)
        stretch_y = rng.uniform(0.94, 1.1)
        road_half_width = int(rng.integers(64, 80)) if road_half_width >= 80 else int(road_half_width)
        road_half_width = max(60, road_half_width)
        do_s_bend = rng.random() < 0.2
    else:
        base_r = size * rng.uniform(0.30, 0.35)
        stretch_x = rng.uniform(0.95, 1.08)
        stretch_y = rng.uniform(0.95, 1.08)
        road_half_width = max(68, int(road_half_width))  # Easy stays wide.
        do_s_bend = False

    ts = np.linspace(0, 2 * math.pi, n_samples, endpoint=False)  # Angles around the loop.
    radii = fourier_radius(ts, rng, base_r, difficulty)  # Bent radii for this difficulty.

    # Build in local coords first, then fit into the canvas -
    # never clip (clipping used to make flat walls on the edges).
    xs = radii * np.cos(ts) * stretch_x
    ys = radii * np.sin(ts) * stretch_y

    # Optional mild S-bend: push a short stretch of the centerline sideways.
    if do_s_bend:
        start = float(rng.uniform(0.25, 0.5))  # Where along the lap the bend starts (0..1).
        span = float(rng.uniform(0.08, 0.14))  # How long the bend lasts.
        amp = float(rng.uniform(12, 26))  # How far sideways to push (pixels).
        for i, t in enumerate(ts):
            phase = (t / (2 * math.pi) - start) % 1.0
            if phase < span:
                wobble = amp * math.sin(2.0 * math.pi * phase / span)
                xs[i] += wobble * math.cos(t)  # Push along the outward normal-ish direction.
                ys[i] += wobble * math.sin(t)
        xs = smooth_closed(xs, passes=4)  # Smooth again so the bend isn't jagged.
        ys = smooth_closed(ys, passes=4)

    # Constant width - variable width looked messy and wasn't worth it.
    w_vals = np.full(n_samples, float(road_half_width))
    max_w = float(road_half_width)
    margin = max_w + 48  # Leave room so the road doesn't touch the canvas edge.
    xs = smooth_closed(xs, passes=3)
    ys = smooth_closed(ys, passes=3)
    # Scale the whole loop so it fits inside the canvas with that margin.
    avail = size * 0.5 - margin
    sx = avail / max(float(np.max(np.abs(xs))), 1.0)
    sy = avail / max(float(np.max(np.abs(ys))), 1.0)
    s = min(sx, sy) * 0.98  # Slightly under-scale so we don't kiss the edge.
    xs = cx + xs * s  # Move into canvas coordinates.
    ys = cy + ys * s

    # --- rasterize the road onto pygame surfaces ---
    border = pygame.Surface((size, size))  # White = driveable for collisions.
    border.fill((0, 0, 0))
    real = pygame.Surface((size, size))  # Colored version the player / camera sees.
    real.fill((18, 20, 26))  # Dark background.

    pts = [(int(round(x)), int(round(y))) for x, y in zip(xs, ys)]  # Integer pixel points.
    n = len(pts)
    hw = max(24, int(round(max_w)))  # Half-width in pixels for drawing.
    # Thick line ribbon + end caps = continuous road (no scalloped circle stamps).
    shoulder_w = (hw + 5) * 2  # Slightly wider dark shoulder under the road.
    road_w = hw * 2
    # First pass: dark shoulder so the road has a little edge.
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        pygame.draw.line(real, (26, 28, 32), a, b, shoulder_w)
        pygame.draw.circle(real, (26, 28, 32), a, hw + 5)
    # Second pass: white border (collision) + grey road (visual).
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        pygame.draw.line(border, (255, 255, 255), a, b, road_w)
        pygame.draw.circle(border, (255, 255, 255), a, hw)
        pygame.draw.line(real, (64, 66, 72), a, b, road_w)
        pygame.draw.circle(real, (64, 66, 72), a, hw)

    # Centerline dashes on the visual surface (looks a bit more like a real track).
    dash_every = 14
    for i in range(0, n, dash_every):
        if (i // dash_every) % 2 == 0:
            pygame.draw.line(real, (230, 210, 80), pts[i], pts[(i + 6) % n], 3)

    # Checkpoints along the centerline, spaced roughly evenly.
    step = max(1, n_samples // n_checkpoints)
    checkpoints = []
    for i in range(0, n_samples, step):
        if len(checkpoints) >= n_checkpoints:
            break  # Breaks / exits out of the for loop - we have enough.
        checkpoints.append([int(xs[i]), int(ys[i])])
    # If we somehow got too few checkpoints, retry with a different seed / wider road.
    if len(checkpoints) < 8:
        return generate_loop_track(
            seed=seed + 9973,
            size=size,
            road_half_width=int(road_half_width) + 8,
            n_checkpoints=n_checkpoints,
            n_samples=n_samples,
            difficulty='easy',
        )

    # Spawn at the start of the loop, facing along the tangent.
    i0, i1 = 0, min(12, n_samples - 1)
    angle = math.degrees(math.atan2(ys[i1] - ys[i0], xs[i1] - xs[i0])) % 360
    spawn = [[int(xs[i0]), int(ys[i0])], 0, angle]

    # If the spawn pixel somehow isn't on white border, walk outward until we find road.
    rgb = pygame.surfarray.array3d(border)
    sx, sy = spawn[0]
    if rgb[sx, sy, 0] < 250:
        hw = max(22, int(w_vals[0]))
        for rad in range(2, hw + 8):
            found = False
            for a in range(0, 360, 10):
                nx = int(sx + rad * math.cos(math.radians(a)))
                ny = int(sy + rad * math.sin(math.radians(a)))
                if 0 <= nx < size and 0 <= ny < size and rgb[nx, ny, 0] >= 250:
                    spawn[0] = [nx, ny]  # Move spawn onto driveable pixels.
                    found = True
                    break  # Breaks / exits out of the angle loop.
            if found:
                break  # Breaks / exits out of the radius loop.

    return [real, border, [spawn], checkpoints]


# Function to save a quick preview PNG of a map pack (road + checkpoints + spawn).
def save_track_preview(map_pack, path):
    img = map_pack[0].copy()  # Copy the visual surface so we don't draw on the real one.
    for cp in map_pack[3]:
        pygame.draw.circle(img, (80, 120, 255), (int(cp[0]), int(cp[1])), 8)  # Blue = checkpoint.
    sp = map_pack[2][0][0]
    pygame.draw.circle(img, (255, 70, 70), (int(sp[0]), int(sp[1])), 12)  # Red = spawn.
    pygame.image.save(img, path)
