# Import libraries.
import math  # For calculations.
import os  # For file handling.
import random  # For random car colors / sprites.
from math import tan, isfinite  # For steering / turning radius checks.

import pygame  # The game engine.

from paths import CARS_DIR

SCALE = 1  # Used to scale the car body and wheels from world units to pixels.

trackColor = (255, 255, 255, 255)  # Used to know what color can be driven on (white = on-road).

# List of stacked sprite sheets in res/cars/. Each sheet can have a different width / layer count.
# Active sprites live in res/cars/. Extra colors are in misc/cars/ (untracked).
CAR_SPRITES = [
    'BlueCar.png',
]

# Shared textures so every car of the same color can reuse what we already uploaded.
SKID_TEXTURES = {}
SKID_ROT_CACHE = {}  # Cache of rotated skid marks so we don't remake them every frame.
SKID_BASE_SURFACES = {}  # Base (un-rotated) skid surfaces, one set per renderer.
RADAR_DOT_TEXTURES = {}
# Cache of rotated car-layer textures shared across cars that use the same sheet.
SHARED_ROT_CACHE = {}
# Cache of the base (un-rotated) sprite layers loaded from disk.
SHARED_BASE_LAYERS = {}


# Function to clear shared sprite / rotation caches (call once per generation teardown).
def clear_shared_sprite_caches(renderer=None):
    global SHARED_ROT_CACHE, SKID_ROT_CACHE
    to_drop = []  # List of cache keys to remove.
    for key, entry in SHARED_ROT_CACHE.items():
        if renderer is None or key[0] == id(renderer):
            to_drop.append(key)
    for key in to_drop:
        tex_id = SHARED_ROT_CACHE.pop(key)[0]  # Grab the texture id before dropping the entry.
        if renderer is not None:
            renderer.unload_texture(tex_id)  # Free the GPU texture.

    skid_drop = []  # List of skid cache keys to remove.
    for key in SKID_ROT_CACHE:
        if renderer is None or key[0] == id(renderer):
            skid_drop.append(key)
    for key in skid_drop:
        tex_id = SKID_ROT_CACHE.pop(key)[0]
        if renderer is not None:
            renderer.unload_texture(tex_id)


# Function to get (or create) the base CPU surfaces used for skid marks.
def get_skid_base_surfaces(renderer):
    # Surfaces are elongated along X (= car forward at rotation 0).
    key = id(renderer)  # Create var containing this renderer's id, for looking up caches.
    if key in SKID_BASE_SURFACES:
        return SKID_BASE_SURFACES[key]  # Already made  -  just return the cached ones.

    colors = {
        'brake': (180, 30, 30, 255),  # Red-ish for braking marks.
        'speed': (234, 184, 46, 255),  # Yellow-ish for high-speed marks.
        'drift': (20, 20, 20, 255),  # Dark for drift marks.
    }
    surfaces = {}
    for name, color in colors.items():
        surface = pygame.Surface((16, 5), pygame.SRCALPHA)  # Small elongated surface for the mark.
        pygame.draw.rect(surface, color, surface.get_rect(), border_radius=2)  # Draw the mark shape.
        surfaces[name] = surface
    SKID_BASE_SURFACES[key] = surfaces  # Cache them for next time.
    return surfaces


# Function to get a rotated skid texture (cached by angle bucket).
def get_rotated_skid(renderer, mark_type, angle_degrees):
    # Rotate skid so its long axis follows the car / wheel heading.
    bucket = int(round(angle_degrees / 3.0) * 3) % 360  # Round angle to nearest 3 degrees for caching.
    key = (id(renderer), mark_type, bucket)
    cached = SKID_ROT_CACHE.get(key)
    if cached is not None:
        return cached  # Already have this rotation cached.

    base = get_skid_base_surfaces(renderer)[mark_type]  # Grab the un-rotated base surface.
    rotated = pygame.transform.rotate(base, bucket)  # Rotate it to the bucketed angle.
    texture_id = renderer.load_surface(rotated)  # Upload the rotated surface to the GPU.
    entry = (texture_id, rotated.get_width(), rotated.get_height())
    SKID_ROT_CACHE[key] = entry  # Save it so we don't re-upload next time.
    return entry


# Function to pick a radar color based on distance (near = red, mid = yellow, far = green).
def radar_color(dist, max_length):
    t = max(0.0, min(1.0, dist / max(max_length, 1)))  # Normalize distance from 0 to 1.
    t = int(t * 8) / 8.0  # Bucket it so hex strings stay cache-friendly.
    if t < 0.5:
        u = t * 2.0
        r, g, b = 255, int(40 + 215 * u), 40  # Blend from red toward yellow.
    else:
        u = (t - 0.5) * 2.0
        r, g, b = int(255 - 215 * u), 255, 40  # Blend from yellow toward green.
    return "#{:02x}{:02x}{:02x}".format(r, g, b), (r, g, b, 255)


# Function to get (or create) cached outer / inner radar endpoint dot textures.
def get_radar_dot_textures(renderer):
    key = id(renderer)
    if key in RADAR_DOT_TEXTURES:
        return RADAR_DOT_TEXTURES[key]  # Already made for this renderer.

    outer = pygame.Surface((12, 12), pygame.SRCALPHA)
    pygame.draw.circle(outer, (200, 200, 200, 255), (6, 6), 5)  # Outer (lighter) circle.
    inner = pygame.Surface((8, 8), pygame.SRCALPHA)
    pygame.draw.circle(inner, (75, 75, 75, 255), (4, 4), 3)  # Inner (darker) circle.

    textures = {
        'outer': renderer.load_surface(outer),
        'outer_size': outer.get_size(),
        'inner': renderer.load_surface(inner),
        'inner_size': inner.get_size(),
        'colored': {},  # Filled on demand: rgb -> texture_id
    }
    RADAR_DOT_TEXTURES[key] = textures
    return textures


# Function to get a small filled circle tinted for the current ray distance.
def get_colored_radar_dot(renderer, rgba):
    dots = get_radar_dot_textures(renderer)
    key = rgba
    if key in dots['colored']:
        return dots['colored'][key]  # Already have this color cached.
    surface = pygame.Surface((12, 12), pygame.SRCALPHA)
    pygame.draw.circle(surface, rgba, (6, 6), 5)  # Fill with the tint color.
    pygame.draw.circle(surface, (30, 30, 30, 220), (6, 6), 5, 1)  # Dark outline around the dot.
    tex = renderer.load_surface(surface)  # Upload to GPU.
    dots['colored'][key] = tex
    return tex


# Class used to draw a car as stacked sprite-sheet layers (pseudo-3D look).
class StackedSprite:
    def __init__(self, sprite_sheet_path, scale=4.0, renderer=None, cache_interval=3):
        self.sprite_path = sprite_sheet_path  # Path to the sprite sheet file.
        self.scale = scale  # How big to draw each layer.
        self.renderer = renderer  # Shared OpenGL renderer used for blitting.
        self.cache_interval = cache_interval  # Degrees between cached rotation angles.
        self.layer_offset = 0.4 * scale  # How far apart each stacked layer is drawn vertically.

        base_key = (sprite_sheet_path, scale)
        if base_key in SHARED_BASE_LAYERS:
            self.base_layers = SHARED_BASE_LAYERS[base_key]  # Reuse layers already loaded for this sheet.
        else:
            sprite_sheet = pygame.image.load(sprite_sheet_path)  # Load the full sheet from disk.
            try:
                sprite_sheet = sprite_sheet.convert_alpha()  # Convert for faster blitting if display is ready.
            except pygame.error:
                pass
            sheet_w = sprite_sheet.get_width()
            sheet_h = sprite_sheet.get_height()
            cell = sheet_h  # Each layer cell is square: height x height.
            layer_count = max(1, sheet_w // cell)  # How many layers are side-by-side on the sheet.
            scaled_w = int(cell * scale)
            scaled_h = int(cell * scale)
            layers = []
            for i in range(layer_count):
                layer_rect = pygame.Rect(i * cell, 0, cell, cell)  # Rect for this layer on the sheet.
                try:
                    layer_surface = sprite_sheet.subsurface(layer_rect).copy()
                    layers.append(pygame.transform.scale(layer_surface, (scaled_w, scaled_h)))
                except ValueError:
                    print("Error: Subsurface for layer " + str(i) + " is out of bounds on " + str(sprite_sheet_path) + ".")
                    break  # Breaks / exits out of the for loop.
            SHARED_BASE_LAYERS[base_key] = layers  # Cache the scaled layers for other cars.
            self.base_layers = layers

        self.layer_count = len(self.base_layers)  # How many layers this sprite has.

    # Function to get a rotated texture for one layer (shared across cars using the same sheet).
    def get_rotated_texture(self, layer_index, angle_degrees):
        if layer_index >= self.layer_count or self.renderer is None:
            return None, 0, 0  # Nothing to draw / no renderer.

        normalized_angle = int(round(angle_degrees / self.cache_interval) * self.cache_interval) % 360
        key = (id(self.renderer), self.sprite_path, self.scale, self.cache_interval, layer_index, normalized_angle)
        cached = SHARED_ROT_CACHE.get(key)
        if cached is not None:
            return cached  # Already rotated and uploaded.

        base_layer = self.base_layers[layer_index]
        rotated_surface = pygame.transform.rotate(base_layer, normalized_angle)  # Rotate the layer.
        texture_id = self.renderer.load_surface(rotated_surface)  # Upload to GPU.
        entry = (texture_id, rotated_surface.get_width(), rotated_surface.get_height())
        SHARED_ROT_CACHE[key] = entry
        return entry

    # Function to draw every sprite layer to create the stacked / pseudo-3D car look.
    def draw(self, position, rotation, offset):
        if not self.renderer:
            raise RuntimeError("Renderer not initialized for GPU drawing")

        angle_degrees = math.degrees(-rotation)  # Convert radians to degrees for pygame rotate.
        stack_span = (self.layer_count - 1) * self.layer_offset  # Total vertical span of the stack.
        base_y = position.y + stack_span / 2.0  # Center the stack vertically around the car.

        for layer_index in range(self.layer_count):
            texture_id, width, height = self.get_rotated_texture(layer_index, angle_degrees)
            if texture_id is None:
                continue
            screen_x = int(position.x - offset[0])  # World x to screen x.
            screen_y = int(base_y - (layer_index * self.layer_offset) - offset[1])  # Stack higher layers up.
            self.renderer.blit(texture_id, screen_x - width // 2, screen_y - height // 2)

    # Function to clean up this sprite. Rotation textures are shared  -  cleared once via clear_shared_sprite_caches().
    def cleanup(self):
        pass


# Function to do a 2D dot product of two vectors.
def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


# Class used for short-lived tire marks drawn behind the car.
class SkidMark:
    def __init__(self, position, rotation, mark_type="drift"):
        self.position = pygame.Vector2(position)  # Variable to see world position of the mark.
        self.rotation = rotation  # Facing angle when the mark was created.
        self.lifetime = 0.4  # Seconds remaining before the mark fades out.
        self.max_lifetime = 0.4  # Full lifetime, used for alpha fading.
        self.mark_type = mark_type  # "drift", "brake", or "speed".

    # Function to tick lifetime; returns False when the mark should be removed.
    def update(self, dt):
        self.lifetime -= dt  # Count down how long this mark has left.
        return self.lifetime > 0

    # Function to get fade amount from 1 (fresh) to 0 (expired).
    def get_alpha(self):
        return self.lifetime / self.max_lifetime


# Class to be used to create cars.
class Car(pygame.sprite.Sprite):
    def __init__(self, id, map, radar_off=False, renderer=None, sprite_config=None, sprite_scale=4.0):
        super().__init__()

        # Fallback body colors used when stacked sprites are disabled.
        color_options = [
            (141, 180, 131), (120, 200, 100), (131, 141, 180), (100, 120, 200),
            (180, 131, 141), (200, 100, 120), (180, 131, 180), (200, 100, 200),
            (180, 170, 131), (200, 180, 100), (131, 180, 180), (100, 200, 200),
            (255, 100, 100), (100, 255, 100), (100, 100, 255), (255, 255, 100),
        ]
        self.body_color = random.choice(color_options)  # Pick a random fill color for the flat body.
        self.outline_color = tuple(max(0, int(c * 0.2)) for c in self.body_color)  # Darker outline from the fill.

        self.radar_off = radar_off  # When True, skip radar sensing / drawing.
        self.renderer = renderer  # Shared OpenGL renderer for this car.

        self.id = id  # Unique id for this car in the current generation.
        self.map = map  # [real, border_surface, spawn, checkpoints, reverse_roll]
        self.starting_checkpoint = map[2][1]  # Checkpoint index at spawn.
        self.current_checkpoint = self.starting_checkpoint
        self.checkpoints = map[3]  # List of checkpoint positions.

        # Setup car variables.
        self.position = pygame.Vector2(map[2][0][0], map[2][0][1])  # Variable to see current position of the car on both axes.
        self.rect = pygame.Rect(self.position.x, self.position.y, 0, 0)

        # Optionally start facing the opposite direction on the track.
        if map[4] >= 0.5:
            self.reverse = True
            self.rotation = map[2][2] + 180  # Face the other way when reverse-spawned.
            if self.rotation >= 360:
                self.rotation -= 360
        else:
            self.reverse = False
            self.rotation = map[2][2]  # Used to calculate rotation of the car, and radars.
        self.rotation = math.radians(self.rotation)  # Store rotation in radians for physics math.

        self.radar_length = 300  # Set the range of the cars radars.
        self.radar_period = 5  # How often (in frames) to refresh radar rays.
        self.cumulative_steering = 0  # Used to track total steering used (fitness gate).
        self.radars = []  # List to hold radar data.
        self.is_alive = True  # Variable to allow checking whether the car is alive (should be drawn), or dead.
        self.odometer = 0  # Used to find the distance the car has gone. Currently being used to calculate cars fitness.
        self.lifetime = 0  # Used to check how long the car has been alive (in frames).
        self.checkpoints_completed = 0  # How many checkpoints this car has hit.
        self.laps = 0  # How many full laps this car has finished.
        self.prev_checkpoint_dist = float('inf')  # Last distance to the current checkpoint.
        self.stuck_timer = 0  # Counts frames spent barely moving on open road.
        self.prev_position = self.position.copy()  # Position from the previous reward tick.
        self.smooth_speed = 0  # Smoothed speed reading for rewards.
        self.prev_speed_for_brake = 0  # Speed from last frame, used to see if we're slowing.
        self.prev_heading_err = 0  # Last heading error toward the checkpoint.
        self.prev_steering_input = 0  # Last steering input, used to catch flip-flops.
        self.prev_steering = 0  # Last steering angle, used to catch wobble.

        # Driver inputs written by NEAT each frame.
        self.throttle = 0
        self.steering_input = 0
        self.brake_force = 0

        # Setup physics / vehicle parameters.
        self.speed = 0
        self.velocity = pygame.Vector2(0, 0)  # Variable to see the current speed/velocity of the car on both axes.
        self.acceleration = 0
        self.steering = 0  # Used to see how much to turn the car, i.e. when steering wheel turns, this will change.
        self.length = 40  # The length of the car.
        self.width = 20  # The width of the car.
        self.corners = self.get_corners()  # Will contain the location of the four corners of the car.
        self.mass = 15000
        self.max_acceleration = 4000  # The maximum amount of acceleration the car can use.
        self.max_braking = 6000000  # How hard the car can brake.
        self.max_steering = math.radians(30)  # The maximum turning angle of the car.
        self.steering_reduction_factor = 0.001  # How much high speed reduces steering.
        self.steering_speed = 8  # How fast the wheel turns toward the target angle.
        self.steering_return_speed = 12  # How fast the wheel returns to center when not steering.
        self.engine_force = 0  # Used to add force to the car, i.e. when the accelerator is pressed, this will go up.
        self.drag_coefficient = 4.257
        self.rolling_resistance = 1280000
        self.wheel_radius = 0.34
        self.gear_ratio = 2.66
        self.diff_ration = 3.42
        self.transmission_efficiency = 0.7
        self.max_torque = 47.5
        self.current_gear = 1
        self.max_speed = 600  # The maximum speed/velocity of the car.
        self.normal_lateral_friction = 480000
        self.drift_lateral_friction = 24000
        self.use_drift_friction = False  # Variable to check whether the car is currently drifting.

        # Wheel layout relative to the car center.
        self.wheel_size = pygame.Vector2(12.5, 7.5)
        self.wheel_positions = [
            (pygame.Vector2(17.5, 15), "front_right"),
            (pygame.Vector2(17.5, -15), "front_left"),
            (pygame.Vector2(-17.5, 15), "back_right"),
            (pygame.Vector2(-17.5, -15), "back_left"),
        ]

        # Setup skid-mark trail state (kept light for performance).
        self.skid_size = pygame.Vector2(14, 6)
        self.skid_marks = []  # List to hold currently alive skid marks.
        self.skid_timer = 0.0
        self.skid_interval = 0.04  # How often (in seconds) to spawn a new mark.
        self.max_skid_marks = 48  # Hard cap so trails can't get too long / slow.

        # Setup car image / stacked sprites. Headless PPO skips the sheet load.
        self.stacked_sprite = None
        self.use_stacked_rendering = False
        if renderer is not None:
            if sprite_config is None:
                sprite_config = random.choice(CAR_SPRITES)  # Pick a random sprite sheet name.
            if isinstance(sprite_config, dict):
                sprite_name = sprite_config.get("path", sprite_config.get("name", CAR_SPRITES[0]))
            else:
                sprite_name = sprite_config
            sprite_path = sprite_name if os.path.isabs(sprite_name) else os.path.join(CARS_DIR, sprite_name)
            self.stacked_sprite = StackedSprite(
                sprite_path, scale=float(sprite_scale), renderer=renderer, cache_interval=3
            )
            self.use_stacked_rendering = True

        # Shared / cached GPU textures for wheels (rotated copies cached by angle).
        self.wheel_texture_id = None
        self.wheel_rot_cache = {}  # angle_bucket -> (texture_id, width, height)
        self.car_body_texture_id = None
        self.wheel_base_surface = None  # Filled in if we have a renderer.
        self.body_base_surface = None  # Filled in if we have a renderer.
        self.body_rot_cache = {}  # angle_bucket -> (texture_id, w, h)
        self.create_gpu_textures()  # Create base wheel + body textures once.

    # Function to create base wheel + body textures once; rotations are cached while driving.
    def create_gpu_textures(self):
        if not self.renderer:
            return

        wheel_surface = pygame.Surface(
            (int(self.wheel_size.x * SCALE), int(self.wheel_size.y * SCALE)), pygame.SRCALPHA
        )
        wheel_rect = wheel_surface.get_rect()
        pygame.draw.rect(wheel_surface, (40, 40, 40), wheel_rect)  # Dark fill for the wheel.
        pygame.draw.rect(wheel_surface, (20, 20, 20), wheel_rect, 1)  # Slightly darker border.
        self.wheel_texture_id = self.renderer.load_surface(wheel_surface)
        self.wheel_base_surface = wheel_surface  # Keep CPU surface around for rotating later.

        # Flat rectangle body (backup normal-view look)  -  used in computer-vision mode.
        body_w = max(1, int(self.length * SCALE))
        body_h = max(1, int(self.width * SCALE))
        body_surface = pygame.Surface((body_w, body_h), pygame.SRCALPHA)
        body_rect = body_surface.get_rect()
        pygame.draw.rect(body_surface, self.body_color, body_rect)  # Fill with the car's body color.
        # Lighter border like backup's (191, 210, 161) relative to fill.
        border = tuple(min(255, int(c + 50)) for c in self.body_color)
        pygame.draw.rect(body_surface, border, body_rect, 2)
        self.body_base_surface = body_surface
        self.car_body_texture_id = self.renderer.load_surface(body_surface)
        self.body_rot_cache = {}  # angle_bucket -> (texture_id, w, h)

    # Function to check whether the car hit a wall (or left the driveable track).
    def check_collision(self, border_mask):
        # border_mask: 2D uint8 array indexed [x, y], nonzero = driveable.
        self.is_alive = True  # Sets the car to alive.
        width, height = border_mask.shape[0], border_mask.shape[1]

        for corner in self.corners:  # for every corner of the car:
            x, y = int(corner[0]), int(corner[1])

            if 0 <= x < width and 0 <= y < height:
                # If the corner is on a pixel that isn't driveable:
                if border_mask[x, y] == 0:
                    self.is_alive = False  # Sets the car to not "alive".
                    break  # Breaks / exits out of the for loop.
            else:
                self.is_alive = False  # Off the map counts as a crash too.
                break  # Breaks / exits out of the for loop.

    # Function to calculate length and endpoints of radars.
    def check_radar(self, degree, border_mask):
        # Cast a ray until it hits a non-driveable pixel or max range.
        # border_mask: 2D uint8 [x, y], nonzero = driveable. Step 8px for speed.
        length = 0  # The initial length of the radar.
        width, height = border_mask.shape[0], border_mask.shape[1]

        dx = math.cos(self.rotation + math.radians(degree))  # X direction of this radar ray.
        dy = math.sin(self.rotation + math.radians(degree))  # Y direction of this radar ray.
        px, py = self.position.x, self.position.y
        x, y = int(px), int(py)
        step = 8  # How many pixels to extend the ray each loop (faster than 1px steps).

        # Loop while the endpoint is still on the map, still on the track, and under max range.
        while 0 <= x < width and 0 <= y < height and length < self.radar_length:
            if border_mask[x, y] == 0:
                break  # Hit a wall  -  stop extending.

            length += step  # Extends the length of the radar until it touches a wall / max range.

            # Calculate the x, and y position of radars endpoint.
            x = int(px + dx * length)  # X endpoint coordinate.
            y = int(py + dy * length)  # Y endpoint coordinate.

        # Adds the data (X, and Y endpoint, and length) from this radar to the radar list.
        self.radars.append([(x, y), float(length)])

    # Function to get world coordinates of the four car corners.
    def get_corners(self):
        cos_rot = math.cos(self.rotation)
        sin_rot = math.sin(self.rotation)

        half_length = (self.length * SCALE) / 2
        half_width = (self.width * SCALE) / 2

        # Local (un-rotated) corners relative to the car center.
        local_corners = [
            pygame.Vector2(half_length, half_width),
            pygame.Vector2(half_length, -half_width),
            pygame.Vector2(-half_length, -half_width),
            pygame.Vector2(-half_length, half_width),
        ]

        world_corners = []
        for c in local_corners:
            # Rotate local corner into world space and add car position.
            world_x = self.position.x + (c.x * cos_rot - c.y * sin_rot)
            world_y = self.position.y + (c.x * sin_rot + c.y * cos_rot)
            world_corners.append(pygame.Vector2(world_x, world_y))

        return world_corners

    # Function to draw radars.
    def draw_radar(self, offset):
        if not self.renderer:
            return

        start_x = self.position.x - offset[0]  # Screen x of the car center.
        start_y = self.position.y - offset[1]  # Screen y of the car center.

        for r in self.radars:  # for every radar in self.radars:
            pos, dist = r  # The position and distance of that radar = the position and distance to be used for drawing.
            end_x = pos[0] - offset[0]
            end_y = pos[1] - offset[1]
            hex_color, unused = radar_color(dist, self.radar_length)  # Color based on how long the ray is.
            self.renderer.draw_line(start_x, start_y, end_x, end_y, hex_color, width=2.0)  # Draw line from car to hit point.

    # Function to get a cached rotated CV body texture (1° buckets).
    def get_rotated_body(self, angle_degrees):
        bucket = int(round(angle_degrees)) % 360  # Round to nearest degree for caching.
        cached = self.body_rot_cache.get(bucket)
        if cached is not None:
            return cached

        rotated = pygame.transform.rotate(self.body_base_surface, bucket)
        texture_id = self.renderer.load_surface(rotated)
        entry = (texture_id, rotated.get_width(), rotated.get_height())
        self.body_rot_cache[bucket] = entry
        return entry

    # Function to draw the flat rectangle car body (used in computer-vision mode).
    def draw_car_body(self, offset):
        if not self.renderer or self.body_base_surface is None:
            return
        angle_degrees = math.degrees(-self.rotation)
        texture_id, width, height = self.get_rotated_body(angle_degrees)
        screen_x = int(self.position.x - offset[0])
        screen_y = int(self.position.y - offset[1])
        self.renderer.blit(texture_id, screen_x - width // 2, screen_y - height // 2)

    # Function to draw the computer-vision / x-ray AI view of the car and track.
    def draw_ai(self, offset, font, border_texture_id=None, draw_background=True, draw_radar=True):
        # Computer-vision view: x-ray border + checkpoints, car as box body + wheels + skids.
        if not self.renderer:
            return

        if draw_background:
            border_surface = self.map[1]  # Grab the border / collision mask image.
            border_rect = border_surface.get_rect()
            border_rect.topleft = (
                border_rect.topleft[0] - int(offset[0]),
                border_rect.topleft[1] - int(offset[1]),
            )
            if border_texture_id is None:
                border_texture_id = self.renderer.load_surface(border_surface)  # Upload if we weren't given one.
                unload_border = True
            else:
                unload_border = False
            self.renderer.blit(border_texture_id, border_rect.x, border_rect.y)
            if unload_border:
                self.renderer.unload_texture(border_texture_id)  # Free the one-off upload.

            for c in enumerate(self.map[3]):  # for every checkpoint index and position:
                adjusted_checkpoint = c[0] - self.starting_checkpoint
                if adjusted_checkpoint < 0:
                    adjusted_checkpoint = len(self.checkpoints) + adjusted_checkpoint

                if self.reverse:
                    adjusted_checkpoint -= len(self.checkpoints) - 1
                    adjusted_checkpoint = abs(adjusted_checkpoint)

                checkpoint_x = c[1][0] - offset[0]
                checkpoint_y = c[1][1] - offset[1]
                color_val = max(0, min(255, int(adjusted_checkpoint)))
                color_hex = "#{:02x}{:02x}{:02x}".format(color_val, color_val, color_val)
                self.renderer.draw_circle(checkpoint_x, checkpoint_y, 50, color_hex)  # Draw checkpoint circle.
                self.renderer.draw_text(
                    checkpoint_x - 6, checkpoint_y - 8, font, str(adjusted_checkpoint), '#FFFFFF'
                )  # Draw checkpoint number.

        self.draw_skid_marks(offset)  # Draw tire marks.
        self.draw_car_body(offset)  # Draw flat body.
        self.draw_wheels(offset)  # Draw wheels.
        if draw_radar and not self.radar_off:
            self.draw_radar(offset)  # Draw radars.

    # Function to set discrete driver inputs from a list of command strings.
    def input(self, commands):
        if "accelerate" in commands:
            self.throttle = .1
        elif "decelerate" in commands:
            self.throttle = -.1
        else:
            self.throttle = 0

        if "brake" in commands:
            self.brake_force = self.max_braking
        else:
            self.brake_force = 0

        if "right" in commands:
            self.steering_input = -1
        elif "left" in commands:
            self.steering_input = 1
        else:
            self.steering_input = 0

    # Function to set continuous PPO-style controls (each channel in [-1, 1], brake uses abs).
    def apply_continuous(self, throttle, brake, steer):
        self.throttle = float(max(-1.0, min(1.0, throttle))) * 0.1
        self.brake_force = self.max_braking if float(brake) > 0.05 else 0
        self.steering_input = float(max(-1.0, min(1.0, steer)))

    # Function to update / refresh various things, such as: car position & angle, calculations, etc..
    def update(self, border, offset, dt):
        if self.is_alive:
            surface_multiplier = 1  # Normal drag / resistance while on the track.
        else:
            surface_multiplier = 4  # Extra drag after crashing (slows the car down faster).

        steering_target = self.max_steering * self.steering_input  # Where the wheel wants to go.
        if self.steering_input == 0:
            self.steering -= self.steering * self.steering_return_speed * dt  # Ease wheel back to center.
        else:
            self.steering += (steering_target - self.steering) * self.steering_speed * dt  # Ease toward target.
        self.steering = (max(-self.max_steering, min(self.steering, self.max_steering)))  # Clamp steering.

        forward = pygame.Vector2(math.cos(self.rotation), math.sin(self.rotation))  # Unit vector pointing forward.
        right = pygame.Vector2(-math.sin(self.rotation), math.cos(self.rotation))  # Unit vector pointing right.

        self.engine_force = self.max_acceleration * self.mass * self.throttle  # Engine force from throttle.
        engine_force_vec = forward * self.engine_force

        self.speed = math.hypot(self.velocity.x, self.velocity.y)  # Current speed from velocity.
        drag_magnitude = .5 * self.drag_coefficient * 2.2 * 1.29 * self.speed * self.speed * surface_multiplier
        if self.speed > 0:
            drag_force_vec = -self.velocity.normalize() * drag_magnitude  # Air drag opposing motion.
            rolling_resistance_force = -self.velocity.normalize() * self.rolling_resistance * surface_multiplier
            brake_force_vec = -self.velocity.normalize() * self.brake_force  # Brake force opposing motion.
        else:
            drag_force_vec = pygame.Vector2(0, 0)
            rolling_resistance_force = pygame.Vector2(0, 0)
            brake_force_vec = pygame.Vector2(0, 0)

        forward_speed = dot(forward, self.velocity)  # How fast we're going forward vs sideways.
        lateral_speed = dot(right, self.velocity)

        if abs(forward_speed) > .1:
            slip_angle = abs(math.atan((lateral_speed / forward_speed)))  # Angle between heading and velocity.
        else:
            slip_angle = 0

        slip_threshold = math.radians(8)
        speed_threshold = 50

        # Check if we should use lower (drift) lateral friction.
        self.use_drift_friction = (slip_angle > slip_threshold) or (
                    self.brake_force > 0 and (abs(forward_speed) > speed_threshold))

        if self.use_drift_friction:
            lateral_friction_coef = self.drift_lateral_friction
        else:
            lateral_friction_coef = self.normal_lateral_friction

        lateral_friction_force = -right * (lateral_speed * lateral_friction_coef)  # Push sideways speed back down.

        net_force = engine_force_vec + drag_force_vec + rolling_resistance_force + brake_force_vec + lateral_friction_force

        acceleration_vec = net_force / self.mass  # F = ma, so a = F / m.
        self.velocity += acceleration_vec * dt  # Add acceleration * deltaTime so it is accurate.

        if self.speed > self.max_speed:
            self.velocity = self.velocity.normalize() * self.max_speed  # Cap top speed.

        if self.speed > .1:
            effective_steering = self.steering / (1 + self.speed * self.steering_reduction_factor)  # Less turn at high speed.
        else:
            effective_steering = 0

        if abs(effective_steering) > 0.0001:
            turning_radius = self.length / tan(effective_steering)  # Calculates the radius how the car should turn.
        else:
            turning_radius = float('inf')

        if isfinite(turning_radius):
            angular_velocity = forward_speed / turning_radius  # Calculates the velocity of the car while turning.
        else:
            angular_velocity = 0  # Sets the cars turning velocity to zero.

        self.lifetime += 1  # Used to calculate how long the car has been alive.
        self.odometer += self.velocity.x + self.velocity.y
        self.odometer /= 2  # Average velocity on both axes.
        self.odometer /= self.lifetime
        self.cumulative_steering += abs(self.steering)  # Track total steering used.

        # Update pose first, then sample the world at the new position.
        self.rotation -= angular_velocity * dt  # Calculate the angle of the car, its direction.
        self.position += self.velocity * dt  # Calculate the position of the car.
        self.corners = self.get_corners()  # Recalculate the four collision points (corners) of the car.
        self.rect.x = self.position.x
        self.rect.y = self.position.y

        self.check_collision(border)  # Check for collisions between the car and walls on the border mask.

        # Radar check  -  every N ticks (watch sets radar_period=1 for smooth rays).
        period = max(1, int(self.radar_period))
        if not self.radar_off and (self.lifetime % period == 0 or not self.radars):
            self.radars.clear()  # Clears / resets / refreshes the data from the radars in self.radars.
            # for every number 10 apart in this range(-55, 56):
            for d in range(-55, 56, 10):
                # Sets the angle each radar should be drawn at in the given range.
                self.check_radar(d, border)
        # Skid marks are updated only for the on-screen car in SimHandler.

    # Function to calculate world positions of all wheels with proper scaling.
    def get_wheel_positions(self):
        cos_rot = math.cos(self.rotation)
        sin_rot = math.sin(self.rotation)

        wheel_world_positions = []
        for local_pos, name in self.wheel_positions:
            scaled_local_x = local_pos.x * SCALE
            scaled_local_y = local_pos.y * SCALE

            # Rotate local wheel offset into world space and add car position.
            world_x = self.position.x + (scaled_local_x * cos_rot - scaled_local_y * sin_rot)
            world_y = self.position.y + (scaled_local_x * sin_rot + scaled_local_y * cos_rot)
            wheel_world_positions.append((pygame.Vector2(world_x, world_y), name))

        return wheel_world_positions

    # Function to spawn / age tire marks without allocating GPU textures per mark.
    def update_skid_marks(self, dt):
        self.skid_timer += dt

        if self.skid_timer >= self.skid_interval:
            self.skid_timer = 0.0

            is_braking = self.brake_force > 0
            is_drifting = self.use_drift_friction
            is_max_speed = self.speed >= self.max_speed * 0.95

            if is_braking or is_drifting or is_max_speed:
                if is_braking:
                    mark_type = "brake"
                elif is_drifting:
                    mark_type = "drift"
                else:
                    mark_type = "speed"

                for wheel_pos, wheel_name in self.get_wheel_positions():
                    # Align marks with that wheel's heading (front wheels include steer).
                    mark_rot = self.rotation
                    if "front" in wheel_name:
                        mark_rot -= self.steering
                    self.skid_marks.append(SkidMark(wheel_pos, mark_rot, mark_type))

                # Drop oldest marks if we hit the cap.
                overflow = len(self.skid_marks) - self.max_skid_marks
                if overflow > 0:
                    del self.skid_marks[:overflow]

        # Keep only marks that are still alive after ticking their lifetime.
        alive_marks = []
        for mark in self.skid_marks:
            if mark.update(dt):
                alive_marks.append(mark)
        self.skid_marks = alive_marks

    # Function to get a cached rotated wheel texture (1° buckets).
    def get_rotated_wheel(self, angle_degrees):
        bucket = int(round(angle_degrees)) % 360
        cached = self.wheel_rot_cache.get(bucket)
        if cached is not None:
            return cached

        rotated = pygame.transform.rotate(self.wheel_base_surface, bucket)
        texture_id = self.renderer.load_surface(rotated)
        entry = (texture_id, rotated.get_width(), rotated.get_height())
        self.wheel_rot_cache[bucket] = entry
        return entry

    # Function to draw wheels using cached rotated textures.
    def draw_wheels(self, offset):
        if not self.renderer or self.wheel_texture_id is None:
            return

        for wheel_pos, wheel_name in self.get_wheel_positions():
            wheel_rotation = self.rotation
            if 'front' in wheel_name:
                wheel_rotation -= self.steering  # Front wheels turn with steering.

            angle_degrees = math.degrees(-wheel_rotation)
            texture_id, width, height = self.get_rotated_wheel(angle_degrees)
            screen_x = wheel_pos.x - offset[0]
            screen_y = wheel_pos.y - offset[1]
            self.renderer.blit(texture_id, screen_x - width / 2, screen_y - height / 2)

    # Function to draw skid marks (long axis follows wheel / car heading).
    def draw_skid_marks(self, offset):
        if not self.renderer:
            return

        for mark in self.skid_marks:
            angle_degrees = math.degrees(-mark.rotation)
            texture_id, width, height = get_rotated_skid(
                self.renderer, mark.mark_type, angle_degrees
            )
            screen_x = mark.position.x - offset[0] - width / 2
            screen_y = mark.position.y - offset[1] - height / 2
            self.renderer.blit(texture_id, screen_x, screen_y, alpha=mark.get_alpha())

    # Function to check if the car is alive.
    def get_alive(self):
        return self.is_alive  # Returns the boolean 'is_alive' to whatever calls the function, can be 'True' or 'False'.

    # Function to grab data from the car (inputs for the neural net).
    def get_data(self):
        # 19-D obs: 12 radars + speed + cp dist/angle + steer + forward/left/right clearance.
        radars = self.radars  # Making a proxy (cloned) variable to access the radar data.
        speed_normalized = min(self.speed / self.max_speed, 1)

        # Setting the input data to be given to the car (you can put anything you want the car to be able to see here).
        ret = [0.0] * 19

        for coord, radar_data in enumerate(radars):  # for every coordinate, and distance (per radar), in the radars list:
            if coord < 12:  # If the amount of coordinates checked is less than 12:
                ret[coord] = min(radar_data[1] / self.radar_length, 1.0)  # Normalize radar length into 0..1.
            else:  # When the 12 values are set:
                break  # Exit the for loop.

        ret[12] = speed_normalized  # Normalized speed.

        next_checkpoint = self.checkpoints[self.current_checkpoint]
        checkpoint_distance = math.sqrt(
            math.pow(next_checkpoint[0] - self.position[0], 2) +
            math.pow(next_checkpoint[1] - self.position[1], 2)
        )  # Distance from car to the next checkpoint.
        checkpoint_distance_normalized = max(0, 1 - (checkpoint_distance / 500.0))

        checkpoint_angle = math.atan2(
            next_checkpoint[1] - self.position[1],
            next_checkpoint[0] - self.position[0]
        )  # Angle from car to the next checkpoint.

        car_angle_degrees = math.degrees(self.rotation)
        relative_angle = (math.degrees(checkpoint_angle) - car_angle_degrees) % 360
        if relative_angle > 180:
            relative_angle -= 360
        relative_angle_normalized = relative_angle / 180.0  # -1..1 relative heading to checkpoint.

        ret[13] = checkpoint_distance_normalized
        ret[14] = relative_angle_normalized
        ret[15] = self.steering / self.max_steering  # Normalized steering amount.

        # Explicit clearances (radar sweep is -55..55 step 10 → 12 rays).
        if len(radars) >= 12:
            forward = min(radars[5][1], radars[6][1])  # -5° / +5°
            left = min(r[1] for r in radars[0:4])     # -55..-25
            right = min(r[1] for r in radars[8:12])    # +25..+55
        elif radars:
            forward = left = right = min(r[1] for r in radars)
        else:
            forward = left = right = self.radar_length
        ret[16] = min(forward / self.radar_length, 1.0)
        ret[17] = min(left / self.radar_length, 1.0)
        ret[18] = min(right / self.radar_length, 1.0)

        return ret  # Returns the list 'ret' containing the inputs for the car to whatever calls this function.

    # Function to calculate the reward that should be given to the car.
    def get_reward(self):
        # Score progress along the checkpoint path. Checkpoints ADVANCE on hit
        # (one-shot), so cars can't farm a single ring forever.
        reward = 0.0
        n = len(self.checkpoints)
        if n == 0:
            return 0.0

        # Target index depends on drive direction around the track.
        if self.reverse:
            target_index = (self.current_checkpoint - 1) % n
        else:
            target_index = self.current_checkpoint % n

        target = self.checkpoints[target_index]
        current_dist = math.hypot(
            target[0] - self.position[0],
            target[1] - self.position[1],
        )  # Distance to the active checkpoint.

        self.smooth_speed = 0.9 * self.smooth_speed + 0.1 * self.speed  # Smooth out speed a bit for rewards.
        # Progress gated by speed  -  faster approaches pay more.
        speed_gate = 0.0 if self.speed < 22 else min((self.speed - 22) / 30.0, 1.5)

        # Dense shaping: reward getting closer to the active checkpoint.
        if self.prev_checkpoint_dist != float("inf"):
            progress = self.prev_checkpoint_dist - current_dist
            if progress > 0:
                reward += progress * 0.16 * speed_gate
            else:
                reward += progress * 0.22
        self.prev_checkpoint_dist = current_dist

        # Checkpoint hit  -  big bonus scales with speed (carry speed through the gate).
        hit_radius = 70
        if current_dist <= hit_radius:
            speed_frac = min(self.speed / max(self.max_speed * 0.55, 1.0), 1.5)
            cp_bonus = 40.0 + 70.0 * speed_frac + min(self.checkpoints_completed, 24) * 1.5
            reward += cp_bonus
            self.checkpoints_completed += 1
            if self.reverse:
                self.current_checkpoint = target_index
            else:
                self.current_checkpoint = (target_index + 1) % n
            self.prev_checkpoint_dist = float("inf")

            if self.checkpoints_completed > 0 and self.checkpoints_completed % n == 0:
                self.laps += 1
                reward += 350  # Extra bonus for finishing a lap.

        min_wall_dist = min((radar[1] for radar in self.radars), default=1000)
        if len(self.radars) >= 2:
            mid = len(self.radars) // 2
            forward_dist = min(self.radars[mid - 1][1], self.radars[mid][1])  # Closest forward radar.
        else:
            forward_dist = min_wall_dist

        slowing = self.prev_speed_for_brake - self.speed  # How much we slowed down this frame.
        self.prev_speed_for_brake = self.speed

        # SPEED FIRST  -  pace pay whenever there's room; soft taper only when the wall is close.
        pace = min(self.smooth_speed / max(self.max_speed * 0.5, 1.0), 1.4)
        if forward_dist > 90:
            reward += pace * 2.4
        elif forward_dist > 50:
            reward += pace * 1.0
        # else: no pace into a near-certain wall, but don't farm brakes either

        # Only punish suicide charges (very short forward + still fast), not "fast racing".
        if forward_dist < 55 and self.speed > 80 and slowing < 0.5 and self.brake_force <= 0:
            reward -= 1.8
        elif forward_dist < 40 and self.speed > 50:
            reward -= 2.5

        movement_vec = self.position - self.prev_position
        forward_vec = pygame.Vector2(math.cos(self.rotation), math.sin(self.rotation))
        right_vec = pygame.Vector2(-math.sin(self.rotation), math.cos(self.rotation))
        if movement_vec.length() > 0 and self.speed >= 25:
            reward += dot(movement_vec.normalize(), forward_vec) * 0.7  # Reward actually moving forward.
        self.prev_position = self.position.copy()

        # Heading: only reward *improving* aim  -  never pay raw steer (that causes wobble).
        checkpoint_angle = math.atan2(target[1] - self.position[1], target[0] - self.position[0])
        heading_err = (math.degrees(checkpoint_angle) - math.degrees(self.rotation)) % 360
        if heading_err > 180:
            heading_err -= 360
        abs_err = abs(heading_err)
        err_improve = self.prev_heading_err - abs_err
        if err_improve > 0 and self.speed >= 30:
            reward += min(err_improve, 8.0) * 0.06
        self.prev_heading_err = abs_err

        # Light drift pay  -  must not outweigh pace / survival.
        if self.use_drift_friction and self.speed > 70 and min_wall_dist > 40:
            lateral = abs(dot(self.velocity, right_vec))
            reward += min(lateral / max(self.max_speed, 1.0), 0.4) * 1.6
            reward += 0.25

        # Anti-wobble: punish flip-flopping the wheel hard.
        steer_amt = abs(self.steering / self.max_steering)
        if self.prev_steering_input * self.steering_input < 0 and abs(self.steering_input) > 0.2:
            reward -= 0.85
        reward -= abs(self.steering - self.prev_steering) * 0.12
        if abs_err < 12 and steer_amt > 0.35 and self.speed > 40:
            reward -= (steer_amt - 0.35) * 0.8
        self.prev_steering_input = self.steering_input
        self.prev_steering = self.steering

        if min_wall_dist < 30:
            reward -= 2.0  # Big punishment for being very close to a wall.
        elif min_wall_dist < 55:
            reward -= 0.4

        # Crawl tax on open road  -  speed is the point.
        if self.speed < 40 and forward_dist > 100:
            reward -= (40 - self.speed) * 0.06
        if self.speed < 22 and forward_dist > 100:
            self.stuck_timer += 1
        else:
            self.stuck_timer = 0
        if self.stuck_timer > 40:
            reward -= 4.0  # Extra punishment if stuck crawling for too long.

        return reward

    # Function to draw car and radars.
    def draw(self, dt, offset, draw_radar=True, draw_skid=True, draw_wheels=True):
        if not self.renderer:
            raise RuntimeError("Renderer required for GPU drawing")

        if draw_skid:
            self.draw_skid_marks(offset)  # Draw tire marks behind the car.

        if draw_wheels:
            self.draw_wheels(offset)  # Draw the four wheels.
        if self.use_stacked_rendering:
            self.stacked_sprite.draw(self.position, self.rotation, offset)  # Draw stacked sprite body.

        if draw_radar and not self.radar_off:
            self.draw_radar(offset)  # Draw radars.

    # Function to free GPU resources owned by this car.
    def cleanup(self):
        if self.stacked_sprite is not None:
            self.stacked_sprite.cleanup()

        if self.wheel_texture_id and self.renderer:
            self.renderer.unload_texture(self.wheel_texture_id)
            self.wheel_texture_id = None

        if self.car_body_texture_id and self.renderer:
            self.renderer.unload_texture(self.car_body_texture_id)
            self.car_body_texture_id = None

        for texture_id, _, _ in self.wheel_rot_cache.values():
            if self.renderer:
                self.renderer.unload_texture(texture_id)
        self.wheel_rot_cache.clear()

        for texture_id, _, _ in self.body_rot_cache.values():
            if self.renderer:
                self.renderer.unload_texture(texture_id)
        self.body_rot_cache.clear()

        self.skid_marks.clear()  # Clear any leftover tire marks.
