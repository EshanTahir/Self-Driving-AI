# Import libraries.
import math  # For calculations.
import os  # For file handling.
from math import sin, radians, degrees, tan, isfinite  # For calculations.

import pygame  # The game engine.
import uiHandler
from pygame.math import Vector2  # For calculations.

from paths import IMAGES_DIR

trackColor = (255, 255, 255, 255)  # Used to know what color can be driven on (white = on-road).
radarLength = 300  # Set the range of the cars radars.


# Function to do a 2D dot product of two vectors.
def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


# Class to be used to create cars.
class Car(pygame.sprite.Sprite):
    def __init__(self, id, map, car_image=None, bound_box_length=55, length=40, max_steering=30, max_acceleration=400.0):
        super().__init__()
        self.map = map
        self.position = Vector2(map[2][0][0], map[2][0][1])  # Variable to see current position of the car on both axes.
        self.starting_checkpoint = map[2][1]
        self.current_checkpoint = self.starting_checkpoint
        self.checkpoints = map[3]
        if map[4] >= .5:
            self.reverse = True
            self.angle = map[2][2] + 180
            if self.angle > 360:
                self.angle = self.angle - 360
        else:
            self.reverse = False
            self.angle = map[2][2]  # Used to calculate rotation of the car, and radars.

        self.frames_passed = 0

        # Setup car variables.
        self.last_2_frame_position = self.position
        self.last_2_frame_tick = pygame.time.get_ticks()

        self.id = id
        self.speed = 0
        self.last_speed = 0
        self.velocity = Vector2(0.0, 0.0)  # Variable to see the current speed/velocity of the car on both axes.
        self.bound_box_length = bound_box_length
        self.length = length  # The length of the car.
        self.mass = 1500  # Simple mass used for F = ma style forces.
        self.max_acceleration = max_acceleration  # The maximum amount of acceleration the car can use.
        self.max_steering = max_steering  # The maximum turning angle of the car (degrees).
        self.max_velocity = 266.4  # The maximum speed/velocity of the car.
        self.brake_deceleration = 500  # How much the car slows down when the brake is pressed.
        self.free_deceleration = 40  # How much the car slows down when it is not accelerating.
        self.radar_length = radarLength  # Set the range of the cars radars.

        # Continuous driver inputs (set each frame by the net / keyboard).
        self.throttle = 0.0  # -1..1 throttle amount.
        self.steering_input = 0.0  # -1..1 steer amount.
        self.brake_force = 0.0  # 0..1 brake amount.

        self.acceleration = 0.0  # Used to add speed to the car from throttle.
        self.steering = 0.0  # Used to see how much to turn the car (degrees).

        # Lateral friction / drift parameters (beginner slip model).
        self.normal_lateral_friction = 8.0  # How hard tires fight sideways slide on grip.
        self.drift_lateral_friction = 1.5  # How hard tires fight sideways slide while drifting.
        self.use_drift_friction = False  # Variable to check whether the car is currently drifting.
        self.slip_angle = 0.0  # Angle between heading and velocity.

        self.four_points = []  # Will contain the location of the four corners of the car.
        self.center = [self.position[0] + 56.5, self.position[1] + 27]  # Variable with calculation for center of car.
        self.radars = []  # List to hold radar data.
        self.is_alive = True  # Variable to allow checking whether the car is alive (should be drawn), or dead.
        self.distance = 0  # Used to find the distance the car has gone. Currently being used to calculate cars fitness.
        self.time_spent = 0  # Used to check how long the car has been alive
        self.prev_checkpoint_dist = float('inf')  # Last distance to the current checkpoint (for progress reward).
        self.checkpoints_completed = 0  # How many checkpoints this car has hit.

        # Setup car image.
        # Load car image to the variable: surface.
        if car_image is None:
            car_image = pygame.image.load(os.path.join(IMAGES_DIR, 'SupraCar.png'))
        self.car_image = car_image
        self.surface = car_image
        self.rotate_surface = self.surface  # Create a duplicate variable of car's image to help with rotation of car.

        #spritifying
        self.image = self.surface
        self.rect = self.surface.get_rect()

    # Function to draw radars.
    def draw_radar(self, screen, offset):
        for r in self.radars:  # for every radar in self.radars:
            pos, dist = r  # The position and distance of that radar = the position and distance to be used for drawing.
            pygame.draw.aaline(screen, (0, 0, 0), self.center - offset, pos - offset,
                               2)  # Draw line on map, black color, at the center of the car,  with size 2.
            pygame.draw.circle(screen, (200, 200, 200), pos - offset,
                               5)  # Draw circle on map, white color, at the end of the line, with size 5.
            pygame.draw.circle(screen, (75, 75, 75), pos - offset,
                               3)  # Draw circle on map, cobalt color, at the center of the other circle, with size 3.

    # Function to draw car and radars.
    def draw(self, screen, offset, drawRadar=True):
        surface = self.car_image
        rotated_image = pygame.transform.rotate(surface, self.angle)
        new_rect = rotated_image.get_rect(center=surface.get_rect(topleft=self.position - offset).center)
        screen.blit(rotated_image, new_rect)

        if drawRadar:
            self.draw_radar(screen, offset)  # Draw radars.

    def draw_ai(self, screen, offset, font):
        border_rect = self.map[1].get_rect()
        border_rect.topleft = border_rect.topleft[0] - int(offset[0]), border_rect.topleft[1] - int(
            offset[1])
        pygame.display.get_surface().blit(self.map[1], border_rect)

        for c in enumerate(self.map[3]):

            adjusted_checkpoint = c[0] - self.starting_checkpoint
            if adjusted_checkpoint < 0:
                adjusted_checkpoint = len(self.checkpoints) + adjusted_checkpoint

            if self.reverse:
                adjusted_checkpoint -= len(self.checkpoints) - 1
                adjusted_checkpoint = abs(adjusted_checkpoint)

            pygame.draw.circle(pygame.display.get_surface(), (adjusted_checkpoint, adjusted_checkpoint, adjusted_checkpoint),
                               c[1] - offset, 50)
            uiHandler.draw_text(screen, c[1][0] - offset[0], c[1][1] - offset[1] - 7,
                                font, str(adjusted_checkpoint), rgb=("#FFFFFF"))
            uiHandler.draw_text(screen, c[1][0] - offset[0], c[1][1] - offset[1] + 7,
                                font, str(c[1]), rgb=("#EEEEEE"))

        for e in self.four_points:
            pygame.draw.circle(screen, (100, 100, 100), (e[0] - offset[0], e[1] - offset[1]), 10)

        pygame.draw.aaline(screen, (0, 0, 0), self.four_points[0] - offset, self.four_points[1] - offset)
        pygame.draw.aaline(screen, (0, 0, 0), self.four_points[1] - offset, self.four_points[2] - offset)
        pygame.draw.aaline(screen, (0, 0, 0), self.four_points[2] - offset, self.four_points[3] - offset)
        pygame.draw.aaline(screen, (0, 0, 0), self.four_points[3] - offset, self.four_points[0] - offset)

        pygame.draw.circle(screen, (200, 200, 200), self.center - offset, 12)

        pygame.draw.circle(screen, (255, 255, 255), offset, 10)

        pygame.draw.circle(screen, (75, 75, 75),
                           (screen.get_size()[0] // 2, screen.get_size()[1] // 2), 10)

        self.draw_radar(screen, offset)

    # Function to calculate length and endpoints of radars.
    def check_radar(self, degree, border_mask):
        # Cast a ray until it hits a non-driveable pixel or max range.
        # border_mask: 2D uint8 [x, y], nonzero = driveable.
        length = 0  # The initial length of the radar.
        width, height = border_mask.shape[0], border_mask.shape[1]

        dx = math.cos(math.radians(360 - (self.angle + degree)))  # X direction of this radar ray.
        dy = math.sin(math.radians(360 - (self.angle + degree)))  # Y direction of this radar ray.
        px, py = self.center[0], self.center[1]
        x, y = int(px), int(py)
        step = 4  # How many pixels to extend the ray each loop (faster than 1px steps).

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

    # Function to check whether the car hit a wall (or left the driveable track).
    def check_collision(self, border_mask):
        # border_mask: 2D uint8 array indexed [x, y], nonzero = driveable.
        self.is_alive = True  # Sets the car to alive.
        width, height = border_mask.shape[0], border_mask.shape[1]

        for e in self.four_points:  # for every point in self.four_points (corners of the car):
            x, y = int(e[0]), int(e[1])

            if 0 <= x < width and 0 <= y < height:
                # If the corner is on a pixel that isn't driveable:
                if border_mask[x, y] == 0:
                    self.is_alive = False  # Sets the car to not "alive".
                    break  # Breaks / exits out of the for loop.
            else:
                self.is_alive = False  # Off the map counts as a crash too.
                break  # Breaks / exits out of the for loop.

    # Function to set discrete driver inputs from a list of command strings.
    def input(self, commands):
        if 'accelerate' in commands:
            self.throttle = 1.0
        elif 'decelerate' in commands:
            self.throttle = -0.5
        else:
            self.throttle = 0.0

        if 'brake' in commands:
            self.brake_force = 1.0
        else:
            self.brake_force = 0.0

        if 'right' in commands:
            self.steering_input = -1.0
        elif 'left' in commands:
            self.steering_input = 1.0
        else:
            self.steering_input = 0.0

    # Function to set continuous PPO-style controls (each channel in [-1, 1], brake uses abs).
    def apply_continuous(self, throttle, brake, steer):
        self.throttle = float(max(-1.0, min(1.0, throttle)))
        self.brake_force = 1.0 if float(brake) > 0.05 else 0.0
        self.steering_input = float(max(-1.0, min(1.0, steer)))

    # Function to update / refresh various things in program, such as: car position & angle, calculations, etc..
    def update(self, border, offset, dt):
        self.rect.center = self.center
        self.frames_passed += 1

        # Ease steering toward the input, and ease throttle into acceleration.
        self.steering = self.max_steering * self.steering_input  # Target steer from continuous input.
        self.acceleration = self.max_acceleration * self.throttle  # Engine push from throttle.

        # Heading unit vectors (angle is stored in degrees like the online car).
        forward = Vector2(math.cos(radians(-self.angle)), math.sin(radians(-self.angle)))
        right = Vector2(-math.sin(radians(-self.angle)), math.cos(radians(-self.angle)))

        # World-space engine force along heading.
        engine_force = forward * (self.acceleration * self.mass)

        # Apply brake as force opposing current velocity.
        if self.brake_force > 0 and self.velocity.length() > 0.1:
            brake_force = -self.velocity.normalize() * (self.brake_deceleration * self.brake_force * self.mass)
        else:
            brake_force = Vector2(0, 0)

        # Free roll slowdown when not on the gas / brake.
        if self.throttle == 0 and self.brake_force == 0 and self.velocity.length() > 0.1:
            drag_force = -self.velocity.normalize() * (self.free_deceleration * self.mass)
        else:
            drag_force = Vector2(0, 0)

        # Split velocity into forward vs sideways for slip.
        forward_speed = dot(forward, self.velocity)
        lateral_speed = dot(right, self.velocity)

        if abs(forward_speed) > 0.1:
            self.slip_angle = abs(math.atan(lateral_speed / forward_speed))  # Angle between heading and velocity.
        else:
            self.slip_angle = 0.0

        slip_threshold = radians(8)
        speed_threshold = 50

        # Check if we should use lower (drift) lateral friction.
        self.use_drift_friction = (self.slip_angle > slip_threshold) or (
            self.brake_force > 0 and abs(forward_speed) > speed_threshold
        )

        if self.use_drift_friction:
            lateral_friction_coef = self.drift_lateral_friction
        else:
            lateral_friction_coef = self.normal_lateral_friction

        # Push sideways speed back down (grip vs drift).
        lateral_friction_force = -right * (lateral_speed * lateral_friction_coef * self.mass)

        net_force = engine_force + brake_force + drag_force + lateral_friction_force
        acceleration_vec = net_force / self.mass  # F = ma, so a = F / m.
        self.velocity += acceleration_vec * dt  # Add acceleration * deltaTime so it is accurate.

        self.speed = self.velocity.length()  # Current speed from velocity.
        if self.speed > self.max_velocity:
            self.velocity = self.velocity.normalize() * self.max_velocity  # Cap top speed.

        if abs(self.steering) > 0.1 and abs(forward_speed) > 0.1:
            turning_radius = self.length / tan(radians(self.steering))  # Calculates the radius how the car should turn.
            if isfinite(turning_radius):
                angular_velocity = forward_speed / turning_radius  # Calculates the velocity of the car while turning.
            else:
                angular_velocity = 0
        else:
            angular_velocity = 0  # Sets the cars turning velocity to zero.

        self.position += self.velocity * dt * 0.5  # Calculate the position of the car.
        self.angle += degrees(angular_velocity) * dt  # Calculate the angle of the car, its direction.
        self.position += self.velocity * dt * 0.5  # Calculate the position of the car, again.

        self.time_spent += 1  # Used to calculate distance the car is driven.

        # Calculate the 4 collision points (corners) of the car.
        self.center = [int(self.position[0]) + 56.5, int(self.position[1]) + 27]  # Calculate center of car.

        # Calculate the left top corner of the car.
        left_top = [self.center[0] + math.cos(math.radians(360 - (self.angle + 30))) * self.bound_box_length,
                    self.center[1] + math.sin(math.radians(360 - (self.angle + 30))) * self.bound_box_length]

        # Calculate the right top corner of the car.
        right_top = [self.center[0] + math.cos(math.radians(360 - (self.angle + 150))) * self.bound_box_length,
                     self.center[1] + math.sin(math.radians(360 - (self.angle + 150))) * self.bound_box_length]

        # Calculate the left bottom corner of the car.
        left_bottom = [self.center[0] + math.cos(math.radians(360 - (self.angle + 210))) * self.bound_box_length,
                       self.center[1] + math.sin(math.radians(360 - (self.angle + 210))) * self.bound_box_length]

        # Calculate the right bottom corner of the car.
        right_bottom = [self.center[0] + math.cos(math.radians(360 - (self.angle + 330))) * self.bound_box_length,
                        self.center[1] + math.sin(math.radians(360 - (self.angle + 330))) * self.bound_box_length]

        # Add the calculated four corners to the four_points list.
        self.four_points = [left_top, right_top, left_bottom, right_bottom]

        # Calculate the distance the car has driven.
        self.distance += (self.velocity[0] + self.velocity[1])
        self.distance = self.distance / 2
        self.distance = self.distance / self.time_spent

        self.check_collision(border)  # Check for collisions between the car and walls on the border mask.
        self.radars.clear()  # Clears / resets / refreshes the data from the radars in self.radars.

        # for every number 10 apart in this range(-55, 56) → 12 radar rays:
        for d in range(-55, 56, 10):
            # Sets the angle each radar should be drawn at in the given range.
            self.check_radar(d, border)

    # Function to grab data from the car (inputs for the neural net).
    def get_data(self):
        # 16-D obs: 12 radars + speed + cp dist/angle + steer  -  no clearances yet.
        radars = self.radars  # Making a proxy (cloned) variable to access the radar data.
        speed_normalized = min(self.speed / self.max_velocity, 1.0)

        # Setting the input data to be given to the car (you can put anything you want the car to be able to see here).
        ret = [0.0] * 16

        for coord, radar_data in enumerate(radars):  # for every coordinate, and distance (per radar), in the radars list:
            if coord < 12:  # If the amount of coordinates checked is less than 12:
                ret[coord] = min(radar_data[1] / self.radar_length, 1.0)  # Normalize radar length into 0..1.
            else:  # When the 12 values are set:
                break  # Exit the for loop.

        ret[12] = speed_normalized  # Normalized speed.

        next_checkpoint = self.checkpoints[self.current_checkpoint]
        checkpoint_distance = math.sqrt(
            math.pow(next_checkpoint[0] - self.center[0], 2) +
            math.pow(next_checkpoint[1] - self.center[1], 2)
        )  # Distance from car to the next checkpoint.
        checkpoint_distance_normalized = max(0, 1 - (checkpoint_distance / 500.0))

        checkpoint_angle = math.atan2(
            next_checkpoint[1] - self.center[1],
            next_checkpoint[0] - self.center[0]
        )  # Angle from car to the next checkpoint.

        relative_angle = (math.degrees(checkpoint_angle) - self.angle) % 360
        if relative_angle > 180:
            relative_angle -= 360
        relative_angle_normalized = relative_angle / 180.0  # -1..1 relative heading to checkpoint.

        ret[13] = checkpoint_distance_normalized
        ret[14] = relative_angle_normalized
        ret[15] = self.steering / self.max_steering  # Normalized steering amount.

        return ret  # Returns the list 'ret' containing the inputs for the car to whatever calls this function.

    # Function to check if the car is alive.
    def get_alive(self):
        return self.is_alive  # Returns the boolean 'is_alive' to whatever calls the function, can be 'True' or 'False'.

    # Function to calculate the reward that should be given to the car.
    def get_reward(self):
        # Basic reward: checkpoint progress + a little speed pay (no anti-wobble / drift yet).
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
            target[0] - self.center[0],
            target[1] - self.center[1],
        )  # Distance to the active checkpoint.

        # Dense shaping: reward getting closer to the active checkpoint.
        if self.prev_checkpoint_dist != float('inf'):
            progress = self.prev_checkpoint_dist - current_dist
            reward += progress * 0.2
        self.prev_checkpoint_dist = current_dist

        # Checkpoint hit  -  big bonus, then advance.
        if current_dist <= 60:
            reward += 50.0 + min(self.speed / 50.0, 2.0) * 20.0
            self.checkpoints_completed += 1
            if self.reverse:
                self.current_checkpoint = target_index
            else:
                self.current_checkpoint = (target_index + 1) % n
            self.prev_checkpoint_dist = float('inf')

        # Light speed pay so crawling is discouraged.
        reward += min(self.speed / self.max_velocity, 1.0) * 0.5

        return reward
