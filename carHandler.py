# Import libraries.
import math  # For calculations.
import os  # For file handling.
from math import sin, radians, degrees  # For calculations.

import pygame  # The game engine.
import uiHandler
from pygame.math import Vector2  # For calculations.
from math import copysign  # For calculations.
current_dir = os.path.dirname(os.path.abspath(__file__))  # Create var containing the current directory, for all OS.
image_dir = os.path.join(current_dir, 'Images')  # Create var containing the images directory, for all OS.

trackColor = (255, 255, 255, 255)  # Used to know what color can be driven on.
radarLength = 300  # Set the range of the cars radars.


# Class to be used to create cars.
class Car(pygame.sprite.Sprite):
    def __init__(self, id, map, car_image=pygame.image.load(os.path.join(image_dir, 'SupraCar.png')), bound_box_length=55, length=3.53, max_steering=30, max_acceleration=40.0):
        super().__init__()
        self.map = map
        self.position = Vector2(map[2][0][0], map[2][0][1])  # Variable to see current position of the car on both axes.
        self.starting_checkpoint = map[2][1]
        self.current_checkpoint = self.starting_checkpoint
        self.checkpoints = map[3]
        if map[4] >=.5:
            self.reverse = True
            self.angle = map[2][2]+180
            if self.angle >360:
                self.angle = self.angle-360
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
        self.max_acceleration = max_acceleration  # The maximum amount of speed/velocity the car can gain per second.
        self.max_steering = max_steering  # The maximum turning angle of the car.
        self.max_velocity = 266.4  # The maximum speed/velocity of the car.
        self.brake_deceleration = 100  # How much the car slows down when the brake is pressed.
        self.free_deceleration = 20  # How much the car slows down when it is not accelerating, decelerating, etc..

        self.acceleration = 0.0  # Used to add speed to the car, i.e. when the accelerator is pressed, this will go up.
        self.steering = 0.0  # Used to see how much to turn the car, i.e. when steering wheel turns, this will change.

        self.four_points = []  # Will contain the location of the four corners of the car.
        self.center = [self.position[0] + 56.5, self.position[1] + 27]  # Variable with calculation for center of car.
        self.radars = []  # List to hold radar data.
        self.is_alive = True  # Variable to allow checking whether the car is alive (should be drawn), or dead.
        self.distance = 0  # Used to find the distance the car has gone. Currently being used to calculate cars fitness.
        self.time_spent = 0  # Used to check how long the car has been alive

        # Setup car image.
        # Load car image to the variable: surface.
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
            pygame.draw.aaline(screen, (0, 0, 0), self.center-offset, pos-offset,
                               2)  # Draw line on map, black color, at the center of the car,  with size 2.
            pygame.draw.circle(screen, (200, 200, 200), pos-offset,
                               5)  # Draw circle on map, white color, at the end of the line, with size 5.
            pygame.draw.circle(screen, (75, 75, 75), pos-offset,
                               3)  # Draw circle on map, cobalt color, at the center of the other circle, with size 3.

    # Function to draw car and radars.
    def draw(self, screen, offset, drawRadar=True):
        surface = self.car_image
        rotated_image = pygame.transform.rotate(surface, self.angle)
        new_rect = rotated_image.get_rect(center=surface.get_rect(topleft=self.position-offset).center)
        screen.blit(rotated_image, new_rect)

        if drawRadar:
            self.draw_radar(screen, offset)  # Draw radars.

    def draw_ai(self, screen, offset, font):
        border_rect = self.map[1].get_rect()
        border_rect.topleft = border_rect.topleft[0] - int(offset[0]), border_rect.topleft[1] - int(
            offset[1])
        pygame.display.get_surface().blit(self.map[1], border_rect)

        for c in enumerate(self.map[3]):

            adjusted_checkpoint = c[0]-self.starting_checkpoint
            if adjusted_checkpoint < 0:
                adjusted_checkpoint = len(self.checkpoints)+adjusted_checkpoint

            if self.reverse:
                adjusted_checkpoint -= len(self.checkpoints)-1
                adjusted_checkpoint = abs(adjusted_checkpoint)

            pygame.draw.circle(pygame.display.get_surface(), (adjusted_checkpoint, adjusted_checkpoint, adjusted_checkpoint),
                               c[1] - offset, 50)
            uiHandler.draw_text(screen, c[1][0] - offset[0], c[1][1] - offset[1]-7,
                                font, str(adjusted_checkpoint), rgb=("#FFFFFF"))
            uiHandler.draw_text(screen, c[1][0] - offset[0], c[1][1] - offset[1]+7,
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
    def check_radar(self, degree, border):
        length = 0  # The initial length of the radar.

        # Calculate the x, and y position of radars endpoint.
        x = int(self.center[0] + math.cos(math.radians(360 - (self.angle + degree))) * length)  # X endpoint coordinate.
        y = int(self.center[1] + math.sin(math.radians(360 - (self.angle + degree))) * length)  # Y endpoint coordinate.

        # Loop to run while the position of the radars endpoint (x, and y), on the 'border'(b&w image for collisions),
        # is the same color as the track, and while the radar is still shorter than its maximum range (radarLength).
        while border.get_at((x, y)) == trackColor and length < radarLength:
            length += 1  # Extends the length of the radar (will stop at 300), until it touches a wall.

            # Calculate the x, and y position of radars endpoint.
            x = int(self.center[0] + math.cos(math.radians(360 - (self.angle + degree))) * length)  # X endpoint coordinate.
            y = int(self.center[1] + math.sin(math.radians(360 - (self.angle + degree))) * length)  # Y endpoint coordinate.

        # Calculate the length of the radar (length var cant be used because the radars are angled).
        dist = int(math.sqrt(math.pow(x - self.center[0], 2) + math.pow(y - self.center[1], 2)))


        # Adds the data (X, and Y endpoint, and length) from this radar to the, radar list.
        self.radars.append([(x, y), dist])

    # Function to check whether the car hit a wall (or in the future, a checkpoint).
    def check_collision(self, border):
        self.is_alive = True  # Sets the car to alive.
        for e in self.four_points:  # for every point in self.four_points (corners of the car):
            # If the corner is touching a pixel in 'border' that isn't the same color as te track:
            if border.get_at((int(e[0]), int(e[1]))) != trackColor:
                self.is_alive = False  # Sets the car to not "alive".
                break  # Breaks / exits out of the for loop.

    # Functions to define car movements:
    def accelerate(self, dt):
        if self.velocity.x < 0:
            self.acceleration = 10
        else:
            self.acceleration += 30 * dt

    def decelerate(self,dt):
        if self.velocity.x > 0:
            self.acceleration = -10
        else:
            self.acceleration -= 30 * dt

    def brake(self, dt):
        if abs(self.velocity.x) > dt * self.brake_deceleration:
            self.acceleration = -copysign(self.brake_deceleration, self.velocity.x)
        else:
            if dt!= 0:
                self.acceleration = -self.velocity.x / dt
            else:
                self.acceleration = self.acceleration

    def turnLeft(self, dt):
        self.steering += 40 * dt
    def turnRight(self, dt):
        self.steering -= 40 * dt

    def blank1(self, dt):
        if abs(self.velocity.x) > dt * self.free_deceleration:
            self.acceleration = -copysign(self.free_deceleration, self.velocity.x)
        else:
            if dt != 0:
                self.acceleration = -self.velocity.x / dt

    def blank2(self, dt):
        self.steering = 0

    # Function to update / refresh various things in program, such as: car position & angle, calculations, etc..
    def update(self, border, offset, dt):
        self.rect.center = self.center
        self.frames_passed+=1
        # Add to the velocity by the amount the car is accelerating and multiply the acceleration by deltaTime so
        # that it is accurate.
        self.velocity += (self.acceleration * dt, 0)

        # Velocity calculation, not sure how it works.
        self.velocity.x = max(float(-self.max_velocity), min(self.velocity.x, float(self.max_velocity)))

        if self.steering:  # Checks if the car is turning / steering (or at least going to).
            turning_radius = self.length / sin(radians(self.steering))  # Calculates the radius how the car should turn.
            angular_velocity = self.velocity.x / turning_radius  # Calculates the velocity of the car while turning.
        else:  # If its not turning, then:
            angular_velocity = 0  # Sets the cars turning velocity to zero.

        # Revert steering and throttle back to 0 when not steering
        if self.steering >=.4:
            self.steering-=20*dt
        if self.steering <=-.1:
            self.steering+=20*dt
        elif -.3 < self.steering < .3:
            self.steering = 0

        if self.acceleration >=.1:
            self.acceleration-=10*dt
        if self.acceleration <=-.1:
            self.acceleration+=10*dt
        elif -.3 < self.acceleration < .3:
            self.acceleration = 0

        self.position += self.velocity.rotate(-self.angle) * dt * 0.5  # Calculate the position of the car.
        self.angle += degrees(angular_velocity) * dt  # Calculate the angle of the car, its direction.
        self.position += self.velocity.rotate(-self.angle) * dt * 0.5  # Calculate the position of the car, again.

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

        # Calculate the distance the car has driven. Adds the velocity of the car on the x and y axes. Then divides them
        # by 2, to get average velocity, and divides the velocity (currently stored in distance), by the time spent
        # driving.
        self.distance += (self.velocity[0] + self.velocity[1])
        self.distance = self.distance / 2
        self.distance = self.distance / self.time_spent

        self.check_collision(border)  # Check for collisions between the car, wall & gate-points on the border image.
        self.radars.clear()  # Clears / resets / refreshes the data from the radars in self.radars.

        # for every number 20 apart in this range(-180, 180), 360/20:
        for d in range(-180, 180, 20):
            # Sets the angle each radar should be drawn at in the given range, 36 degrees apart.
            self.check_radar(d, border)

    # Function to grab data from the car.
    def get_data(self):
        radars = self.radars  # Making a proxy (cloned) variable to access the radar data.

        if self.frames_passed == 2:
            distance = [self.rect.center[0]-self.last_2_frame_position[0], self.rect.center[1]-self.last_2_frame_position[1]]
            distance = [distance[0]*.625, distance[1]*.625]
            distance = distance[0] + distance[1]
            distance /= 2
            time = pygame.time.get_ticks()/1000 - self.last_2_frame_tick
            try:
                self.speed = distance / time
            except:
                self.speed = self.last_speed

            self.speed = abs(self.speed)
            self.last_2_frame_position = self.rect.center
            self.last_2_frame_tick = pygame.time.get_ticks()/1000
            self.last_speed = self.speed
            self.frames_passed = 0

        if self.steering < 0:
            steering = 1
        elif self.steering > 0:
            steering = 2
        elif self.steering == 0:
            steering = 0

        # Setting the input data to be given to the car (you can put anything you want the car to be able to see here,
        # i.e. more radars), first 10 zeros are radars, last 2 are the speed and angle of car.
        ret = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, self.speed, abs(self.steering), steering]

        for coord, dist in enumerate(radars):  # for every coordinate, and distance (per radar), in the radars list:
            if coord < 18:  # If the amount of coordinates checked is less than 15:
                ret[coord] = int(dist[1] / 30)  # The first 10 values in 'ret' will be changed to the distance / 30.
            else:  # When the 15 values are set:
                break  # Exit the for loop.
        return ret  # Returns the list 'ret' containing the inputs for the car to whatever calls this function.

    # Function to check if the car is alive.
    def get_alive(self):
        return self.is_alive  # Returns the boolean 'is_alive' to whatever calls the function, can be 'True' or 'False'.

    # Function to calculate the reward that should be given to the car.
    def get_reward(self):
        reward = 0
        if self.reverse:
            if int(math.sqrt(math.pow(self.checkpoints[self.current_checkpoint-1][0] - self.center[0], 2) + math.pow(self.checkpoints[self.current_checkpoint-1][1] - self.center[1], 2))) <= 50:
                reward += 100
                if self.current_checkpoint-1 == len(self.checkpoints):
                    self.current_checkpoint = 0
                else:
                    self.current_checkpoint -= 1
        elif not self.reverse:
            if int(math.sqrt(math.pow(self.checkpoints[self.current_checkpoint][0] - self.center[0], 2) + math.pow(self.checkpoints[self.current_checkpoint][1] - self.center[1], 2))) <= 50:
                reward += 100
                if self.current_checkpoint+1 == len(self.checkpoints):
                    self.current_checkpoint = 0
                else:
                    self.current_checkpoint += 1

        return reward
