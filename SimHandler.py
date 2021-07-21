# ToDo: Features to add:
# ToDo: Add scrolling functionality to the program so the car is always visible.
# ToDo: Replace distance driven fitness reward with gates to reward fitness when driven over by car.
# ToDo: Add GUI, start button, skip generation button, button to toggle view of all cars at once.
# ToDo: Add weather changes, obstacles, and environment changes to simulation.
# Todo: Add a neural net viewer.
# Todo: Cleanup unused code, neaten current code, use more variables for calculations, use better names for vars, etc..
# ToDo: Scan all lines of code and write detailed comments.

# FixMe: Bugs to fix:
# FixMe: Time counter freezes at 120 seconds.

# Import libraries.
import neat  # The genetic algorithm.
import pygame  # The game engine.
import sys  # To be used for closing program.
import os  # For file handling.
import math  # For calculations.
from math import copysign, sin, radians, degrees  # For calculations
from pygame.math import Vector2  # For calculations

# Startup variables.
current_dir = os.path.dirname(os.path.abspath(__file__))  # Create var containing the current directory, for all OS.
image_dir = os.path.join(current_dir, 'Images')  # Create var containing the images directory, for all OS.
misc_dir = os.path.join(current_dir, 'Miscellaneous') # Create var containing the misc directory, for all OS.
icon = pygame.image.load(os.path.join(image_dir, 'ai.png'))  # Load program icon.
pygame.display.set_icon(icon)  # Set program icon.
pygame.display.set_caption('NEAT Driving Simulator')  # Set program title.
screen_width = 1500  # Set program x resolution.
screen_height = 800  # set program y resolution.
generation = 0  # Variable to count generations.
trackColor = (255, 255, 255, 255)  # Used to know what color can be driven on.
gateColor = (95, 208, 228, 255)  # Used to know what color when driven on, gives a reward. ToDo: Checkpoint related.
radarLength = 300  # Set the range of the cars radars.
startPosX = 750  # The starting position of cars on the x-axis.
startPosY = 700  # The starting position of cars on the y-axis.

# Part 1 of Program
# Class to be used to create cars.
class Car:
    def __init__(self, x=startPosX, y=startPosY, angle=0.0, length=4, max_steering=25, max_acceleration=20.0):

        # Setup car variables.
        self.position = Vector2(x, y)  # Variable to see current position of the car on both axes.
        self.velocity = Vector2(0.0, 0.0)  # Variable to see the current speed/velocity of the car on both axes.
        self.angle = angle  # Used to calculate rotation of the car, and radars.
        self.length = length  # The length of the car.
        self.max_acceleration = max_acceleration  # The maximum amount of speed/velocity the car can gain per second.
        self.max_steering = max_steering  # The maximum turning angle of the car.
        self.max_velocity = 120  # The maximum speed/velocity of the car.
        self.brake_deceleration = 10  # How much the car slows down when the brake is pressed.
        self.free_deceleration = 2  # How much the car slows down when it is not accelerating, decelerating, etc..

        self.acceleration = 0.0  # Used to add speed to the car, i.e. when the accelerator is pressed, this will go up.
        self.steering = 0.0  # Used to see how much to turn the car, i.e. when steering wheel turns, this will change.

        self.four_points = []  # Will contain the location of the four corners of the car.
        self.center = [self.position[0] + 56.5, self.position[1] + 27]  # Variable with calculation for center of car.
        self.radars = []  # List to hold radar data.
        self.is_alive = True  # Variable to allow checking whether the car is alive (should be drawn), or dead.
        self.distance = 0  # Used to find the distance the car has gone. Currently being used to calculate cars fitness.
        self.time_spent = 0  # Used to check how long the car has been alive
        self.cpp = 0  # Used to check how much checkpoints the car has passed. ToDo: Checkpoint Related.

        # Setup car image.
        self.surface = pygame.image.load(os.path.join(image_dir, 'SupraCar.png'))  # Load car image to the variable: surface.
        self.rotate_surface = self.surface  # Create a duplicate variable of car's image to help with rotation of car.

    # Function to draw radars.
    def draw_radar(self, screen):
        for r in self.radars:  # for every radar in self.radars:
            pos, dist = r  # The position and distance of that radar = the position and distance to be used for drawing.
            pygame.draw.aaline(screen, (0, 0, 0), self.center, pos,
                               2)  # Draw line on map, black color, at the center of the car,  with size 2.
            pygame.draw.circle(screen, (255, 255, 255), pos,
                               5)  # Draw circle on map, white color, at the end of the line, with size 5.
            pygame.draw.circle(screen, (0, 80, 181), pos,
                               3)  # Draw circle on map, cobalt color, at the center of the other circle, with size 3.

    # Function to draw car and radars.
    def draw(self, screen):
        surface = pygame.image.load(os.path.join(image_dir, 'SupraCar.png')).convert_alpha()
        rotated_image = pygame.transform.rotate(surface, self.angle)
        new_rect = rotated_image.get_rect(center=surface.get_rect(topleft=self.position).center)
        new_rect.y += 6
        new_rect.x += 7
        screen.blit(rotated_image, new_rect)

        self.draw_radar(screen)  # Draw radars.

    # Function to calculate length and endpoints of radars.
    def check_radar(self, degree, border):
        length = 0  # The initial length of the radar.

        # Calculate the x, and y position of radars endpoint.
        x = int(self.center[0] + math.cos(math.radians(360 - (self.angle + degree))) * length)  # X endpoint coordinate.
        y = int(self.center[1] + math.sin(math.radians(360 - (self.angle + degree))) * length)  # Y endpoint coordinate.

        # Loop to run while the position of the radars endpoint (x, and y), on the 'border'(b&w image for collisions),
        # is the same color as the track, and while the radar is still shorter than its maximum range (radarLength).
        while border.get_at((x, y)) == trackColor and length < radarLength:
            length = length + 1  # Extends the length of the radar (will stop at 300), until it touches a wall.

            # Calculate the x, and y position of radars endpoint.
            x = int(self.center[0] + math.cos(math.radians(360 - (self.angle + degree))) * length)  # X coordinate.
            y = int(self.center[1] + math.sin(math.radians(360 - (self.angle + degree))) * length)  # Y coordinate.

        # Calculate the length of the radar (length var cant be used because the radars are angled).
        dist = int(math.sqrt(math.pow(x - self.center[0], 2) + math.pow(y - self.center[1], 2)))

        self.radars.append([(x, y), dist])  # Adds the data (X, and Y endpoint, and length) from this radar to the,
                                            # radar list.

    # Function to check whether the car hit a wall (or in the future, a checkpoint).
    def check_collision(self, border):
        self.is_alive = True  # Sets the car to alive.
        for e in self.four_points:  # for every point in self.four_points (corners of the car):
            # If the corner is touching a pixel in 'border' that isn't the same color as te track:
            if border.get_at((int(e[0]), int(e[1]))) != trackColor:
                self.is_alive = False  # Sets the car to not "alive".
                break  # Breaks / exits out of the for loop.

        # if map.get_at(self.center) == gateColor: #    ToDo: Checkpoint related.
        #   self.cpp += 1

    # Function to update / refresh various things in program, such as: car position & angle, calculations, etc..
    def update(self, border, dt):

        self.velocity += (self.acceleration * dt, 0)  # Add to the velocity by the amount the car is accelerating
                                                      # and multiply the acceleration by deltaTime so that it is
                                                      # accurate.

        self.velocity.x = max(-self.max_velocity, min(self.velocity.x, self.max_velocity))  # Velocity calculation,
                                                                                            # not sure how it works.

        if self.steering:  # Checks if the car is turning / steering (or at least going to).
            turning_radius = self.length / sin(radians(self.steering))  # Calculates the radius how the car should turn.
            angular_velocity = self.velocity.x / turning_radius  # Calculates the velocity of the car while turning.
        else:  # If its not turning, then:
            angular_velocity = 0  # Sets the cars turning velocity to zero.

        self.position += self.velocity.rotate(-self.angle) * dt * 0.5  # Calculate the position of the car.
        self.angle += degrees(angular_velocity) * dt  # Calculate the angle of the car, its direction.
        self.position += self.velocity.rotate(-self.angle) * dt * 0.5  # Calculate the position of the car, again.

        self.time_spent += 1  # Used to calculate distance the car is driven.

        # Calculate the 4 collision points (corners) of the car.
        self.center = [int(self.position[0]) + 64, int(self.position[1]) + 32]  # Calculate center of car.
        length = 40  # The length of the car.

        # Calculate the left top corner of the car.
        left_top = [self.center[0] + math.cos(math.radians(360 - (self.angle + 30))) * length,
                    self.center[1] + math.sin(math.radians(360 - (self.angle + 30))) * length]

        # Calculate the right top corner of the car.
        right_top = [self.center[0] + math.cos(math.radians(360 - (self.angle + 150))) * length,
                     self.center[1] + math.sin(math.radians(360 - (self.angle + 150))) * length]

        # Calculate the left bottom corner of the car.
        left_bottom = [self.center[0] + math.cos(math.radians(360 - (self.angle + 210))) * length,
                       self.center[1] + math.sin(math.radians(360 - (self.angle + 210))) * length]

        # Calculate the right bottom corner of the car.
        right_bottom = [self.center[0] + math.cos(math.radians(360 - (self.angle + 330))) * length,
                        self.center[1] + math.sin(math.radians(360 - (self.angle + 330))) * length]

        # Add the calculated four corners to the four_points list.
        self.four_points = [left_top, right_top, left_bottom, right_bottom]

        self.distance += (self.velocity[0] + self.velocity[1])  # Calculate the distance the car has driven.
        self.distance = self.distance / 2                       # Adds the velocity of the car on the x and y axes. Then
        self.distance = self.distance / self.time_spent         # divides them by 2, to get average velocity, and
                                                                # divides the velocity (currently stored in distance),
                                                                # by the time spent driving.

        self.check_collision(border)  # Check for collisions between the car, wall & gate-points on the border image.
        self.radars.clear()  # Clears / resets / refreshes the data from the radars in self.radars.

        for d in range(-180, 180, 36):  # for every number 36 apart in this range(-180, 180):
            self.check_radar(d, border)  # Sets the angle each radar should be drawn at in the given range, 36 degrees
                                         # apart.

    # Function to grab data from the car.
    def get_data(self):
        radars = self.radars  # Making a proxy (cloned) variable to access the radar data.
        ret = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, self.velocity[0], self.velocity[1]]  # Setting the input data to be given
                                                                                  # to the car (you can put anything you
                                                                                  # want the car to be able to see here,
                                                                                  # i.e. more radars), first 10 zeros
                                                                                  # are radars, last 2 are the x, and y
                                                                                  # velocities of the car.

        for coord, dist in enumerate(radars):  # for every coordinate, and distance (per radar), in the radars list:
            if coord < 10:  # If the amount of coordinates checked is less than 10:
                ret[coord] = int(dist[1] / 30)  # The first 10 values in 'ret' will be changed to the distance / 30.
            else:  # When the 10 values are set:
                break  # Exit the for loop.
        return ret  # Returns the list 'ret' containing the inputs for the car to whatever calls this function.

    # Function to check if the car is alive.
    def get_alive(self):
        return self.is_alive  # Returns the boolean 'is_alive' to whatever calls the function, can be 'True' or 'False'.

    # Function to calculate the reward that should be given to the car.
    def get_reward(self):
        # return self.cpp # ToDo: Checkpoint related.

        return self.distance / 5000.0  # The 'reward', is added to 'fitness' to see how good the car is at driving.
                                       # The value is retrieved because this line will 'return' the calculation to
                                       # whatever called it.


# Part 2 of Program
# Function to call on to run simulation
def run_car(genomes, conf):  # Genomes are the individual cars dna makeup, species are made up of similar genomes.
    nets = []  # List to hold all the neural networks.
    cars = []  # List to hold all the cars and their data.

    for c, g in genomes:  # c = each car or maybe amount of cars, g = each genome.
        net = neat.nn.FeedForwardNetwork.create(g, conf)  # Use NEAT library to create each neural network,
                                                          # with genome g, using 'conf', the config file.

        nets.append(net)  # Adds each neural network 'net', to the list 'nets' containing the networks.
        g.fitness = 0  # Sets the initial fitness benchmark for each genome to 0.
        cars.append(Car())  # Add each car and the info it contains to the cars list.

    # Initialize and setup game / simulation test place.
    pygame.init()  # Load pygame.
    pygame.event.set_allowed([pygame.QUIT])  # Make sure that pygame only checks to see if the close button is clicked,
                                             # no other button, or key (saves processing time).

    screen = pygame.display.set_mode((screen_width, screen_height))  # Sets up the display surface for the simulation.
    clock = pygame.time.Clock()  # Creates a proxy variable 'clock' to access the in-game clock.
    font = pygame.font.Font(os.path.join(misc_dir, 'Pixelar.ttf'), 20)  # Loads in a font 'Pixelar', with size 20 to the variable 'font'.
    level = pygame.image.load(os.path.join(image_dir, 'map3Flat.png')).convert_alpha()  # Loads in level to be  displayed to the var: 'level'.
    boundary = pygame.image.load(os.path.join(image_dir, 'BorderBB&W.png')).convert()  # Loads in a b&w image to help check for collisions.
    tick = 60  # sets the amount of ticks that should be ticked each time the game is refreshed.
    global generation  # Using 'global' to access the variable 'generation' from outside this loop and function.

    generation += 1  # Each time all cars die or time limit passes, the while loop below is stopped, and it runs the
                     # code in run() again, so it adds to the cars generation each time they all die.

    # Main loop for running the simulation.
    while 1:
        # Setup variables for the loop.
        remain_cars = 0  # Used to check how much cars are alive in total, initially set to 0.
        f_list = []  # A list used to see what car has the highest fitness, all cars fitness are added here and checked.
        m_speed = 0  # A variable used to display the speed of the car with the most fitness.
        m_acceleration = 0  # A variable used to display the acceleration amount of the car with the most fitness.
        m_steering = 0  # A variable used to display the turning angle of the car with the most fitness.
        m_position_x = 0  # A variable used to display the x-coordinate of the car with the most fitness.
        m_position_y = 0  # A variable used to display the y-coordinate of the car with the most fitness.
        m_fitness = 0  # A variable used to display the fitness level of the car with the most fitness.
        dt = clock.get_time() / 1000  # Variable used to calculate delta time.

        for event in pygame.event.get():  # Loop to check if anything that can be pressed was pressed:
            if event.type == pygame.QUIT:  # If the quit button was pressed:
                sys.exit(0)  # Exit the program.

        #
        for index, car in enumerate(cars):  # For neural net ID, and car in the cars list,
            output = nets[index].activate(car.get_data())  # The output that the net 'returns' when given car data.
            i = output.index(max(output))  # i = the max output received from the net (the actual output).

            # Defining what the car does when it outputs certain values (accelerate, decelerate, brake, turn, etc..):
            if i > .5 and i != 1:
                if car.velocity.x < 0:
                    car.acceleration = car.brake_deceleration
                else:
                    car.acceleration += 1 * dt
            elif i < .5 and i != 0:
                if car.velocity.x > 0:
                    car.acceleration = -car.brake_deceleration
                else:
                    car.acceleration -= 1 * dt
            elif i == .5:
                if abs(car.velocity.x) > dt * car.brake_deceleration:
                    car.acceleration = -copysign(car.brake_deceleration, car.velocity.x)
                else:
                    car.acceleration = -car.velocity.x / dt
            else:
                if abs(car.velocity.x) > dt * car.free_deceleration:
                    car.acceleration = -copysign(car.free_deceleration, car.velocity.x)
                else:
                    if dt != 0:
                        car.acceleration = -car.velocity.x / dt
            car.acceleration = max(-car.max_acceleration, min(car.acceleration, car.max_acceleration))

            if i == 1:
                car.steering += 30 * dt
            elif i == 0:
                car.steering -= 30 * dt
            else:
                car.steering = 0
            car.steering = max(-car.max_steering, min(car.steering, car.max_steering))

        for i, car in enumerate(cars):  # for each neural net, and car in cars list:
            if car.get_alive():  # if the car is alive:
                remain_cars += 1  # Add to the remaining cars number,
                car.update(boundary, dt)  # Update the cars position etc..
                genomes[i][1].fitness += car.get_reward()  # Add the reward to the neural networks genomes fitness.
                f_list.append(genomes[i][1].fitness)  # Add each neural networks genomes fitness value to this list.
                f_list.sort()  # Sort all the fitness values (ascending) in this list.

        # Drawing, and statistics.
        screen.blit(level, (0, 0))  # Render the level onto the screen at coordinates (0, 0)
        for i, car in enumerate(cars):  # for each cars neural network and car in the cars list:
            if car.get_alive():  # if that car is alive:
                if genomes[i][1].fitness == max(f_list):  # If the neural networks genomes fitness is the highest:
                    car.surface = car.surface.convert()  # Convert the cars image for faster calculations.

                    # Setting up the variables for statistics.
                    m_acceleration = car.acceleration  # This variable = the same as the best car.
                    m_steering = car.steering  # This variable = the same as the best car.
                    m_position_x = car.center[0]  # This variable = the same as the best car.
                    m_position_y = car.center[1]  # This variable = the same as the best car.
                    m_fitness = genomes[i][1].fitness
                    m_speed = (car.velocity[0] + car.velocity[1])  # This variable = the average speed of the best car.
                    m_speed = m_speed / 2

                    car.draw(screen)  # Draw this car (the best car) to the screen.
                    break  # Break out of this for loop.

        # Check if the generation should end.
        if pygame.time.get_ticks() >= 120000 * generation:  # if the ticks that passed is greater than 120k (120.s)*gen:
            break  # Exit the while loop and end the generation.

        if remain_cars == 0:  # If all cars died:
            break  # Exit the while loop and end the generation.

        #   FixMe: Time freezing at 120 seconds.
        # Setup generation timer.

        gen_time = pygame.time.get_ticks()  # Set the variable to be the same amount of ticks, divide it by 1k to get
        gen_time = gen_time / 1000          # seconds, and divide it by the generation amount to create a timer.
        gen_time = gen_time / generation
        gen_time = str(gen_time)  # Convert the variable to a string from being a number.

        # Convert the data to strings so it can be displayed.
        m_speed = str(m_speed)
        m_acceleration = str(m_acceleration)
        m_steering = str(m_steering)
        m_position_x = str(m_position_x)
        m_position_y = str(m_position_y)
        m_fitness = str(m_fitness)

        # Draw a transparent box for stats to be written on.
        stat_box = pygame.Surface((200, 200))  # Create a surface with (200, 200) resolution.
        stat_box.set_alpha(50)  # Make the surface '50' transparent.
        stat_box.fill((255, 255, 255))  # Set the color of the surface to (255, 255, 255) / black.
        screen.blit(stat_box, (screen_width / 150, screen_height / 1.355932))  # Render box to the screen.

        # Drawing the stats:
        text = font.render("Car generation: " + str(generation), True, (0, 0, 0))  # Text to be drawn, and color.
        text_rect = text.get_rect()  # Grab the rectangle borders for the text.
        text_rect.center = (110, 600)  # Coordinates for text to be drawn at.
        screen.blit(text, text_rect)  # Render 'text' to the screen at the position of 'text_rect'.

        text = font.render("Generation clock: " + gen_time[0:3] + "s", True, (0, 0, 0))  # Text to be drawn, and color.
        text_rect = text.get_rect()  # Grab the rectangle borders for the text.
        text_rect.center = (110, 620)  # Coordinates for text to be drawn at.
        screen.blit(text, text_rect)  # Render 'text' to the screen at the position of 'text_rect'.

        text = font.render("Speed: " + m_speed[0:4] + "mph", True, (0, 0, 0))  # Text to be drawn, and color.
        text_rect = text.get_rect()  # Grab the rectangle borders for the text.
        text_rect.center = (110, 640)  # Coordinates for text to be drawn at.
        screen.blit(text, text_rect)  # Render 'text' to the screen at the position of 'text_rect'.

        text = font.render("Throttle: " + m_acceleration[0:4], True, (0, 0, 0))  # Text to be drawn, and color.
        text_rect = text.get_rect()  # Grab the rectangle borders for the text.
        text_rect.center = (110, 660)  # Coordinates for text to be drawn at.
        screen.blit(text, text_rect)  # Render 'text' to the screen at the position of 'text_rect'.

        text = font.render("Steering: " + m_steering[0:4] + "°", True, (0, 0, 0))  # Text to be drawn, and color.
        text_rect = text.get_rect()  # Grab the rectangle borders for the text.
        text_rect.center = (110, 680)  # Coordinates for text to be drawn at.
        screen.blit(text, text_rect)  # Render 'text' to the screen at the position of 'text_rect'.

        text = font.render("Fitness: " + m_fitness[0:10], True,(0, 0, 0))  # Text to be drawn, and color.
        text_rect = text.get_rect()  # Grab the rectangle borders for the text.
        text_rect.center = (110, 700)  # Coordinates for text to be drawn at.
        screen.blit(text, text_rect)  # Render 'text' to the screen at the position of 'text_rect'.

        text = font.render("Coordinates: " + "(" + str(m_position_x[0:4]) + ", " + str(m_position_y[0:3]) + ")", True,
                           (0, 0, 0))  # Text to be drawn, and color.
        text_rect = text.get_rect()  # Grab the rectangle borders for the text.
        text_rect.center = (110, 720)  # Coordinates for text to be drawn at.
        screen.blit(text, text_rect)  # Render 'text' to the screen at the position of 'text_rect'.

        text = font.render("Remaining cars: " + str(remain_cars), True, (0, 0, 0))  # Text to be drawn, and color.
        text_rect = text.get_rect()  # Grab the rectangle borders for the text.
        text_rect.center = (110, 740)  # Coordinates for text to be drawn at.
        screen.blit(text, text_rect)  # Render 'text' to the screen at the position of 'text_rect'.

        pygame.display.flip()  # Refresh the entire screen (graphically).
        clock.tick_busy_loop(tick)  # Tick the clock by 'ticks' amount.

# Run program.
if __name__ == "__main__":
    sim_length = 1000000
    config_path = "./config-feedforward.txt"  # Set the location for the configuration file.
    config = neat.config.Config(neat.DefaultGenome, neat.DefaultReproduction,
                                neat.DefaultSpeciesSet, neat.DefaultStagnation,
                                config_path)  # Setup NEAT configuration.

    # Create core evolution algorithm class
    p = neat.Population(config)

    # Add reporter for statistical results
    p.add_reporter(neat.StdOutReporter(True))
    stats = neat.StatisticsReporter()
    p.add_reporter(stats)

    # Run NEAT using run_car function, 'sim_length' amount of times.
    p.run(run_car, sim_length)
