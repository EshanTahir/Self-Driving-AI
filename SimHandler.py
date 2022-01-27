# Import libraries.
import os  # For file handling.
import sys  # To be used for closing program.
from math import copysign  # For calculations.

import neat  # The genetic algorithm handler.
import pygame  # The game engine.

import uiHandler
from carHandler import Car

current_dir = os.path.dirname(os.path.abspath(__file__))  # Create var containing the current directory, for all OS.
image_dir = os.path.join(current_dir, 'Images')  # Create var containing the images directory, for all OS.
misc_dir = os.path.join(current_dir, 'Miscellaneous')  # Create var containing the misc directory, for all OS.

icon = pygame.image.load(os.path.join(image_dir, 'ai.png'))  # Load program icon.
pygame.display.set_icon(icon)  # Set program icon.
pygame.display.set_caption('NEAT Driving Simulator')  # Set program title.

screen_width = 1500  # Set program x resolution.
screen_height = 800  # set program y resolution.

generation = 0  # Variable to count generations.


# Function to call on to run simulation
def run_car(genomes, conf):  # Genomes are the individual cars dna makeup, species are made up of similar genomes.
    nets = []  # List to hold all the neural networks.
    cars = []  # List to hold all the cars and their data.

    for c, g in genomes:  # c = each car or maybe amount of cars, g = each genome.
        # Use NEAT library to create each neural network, with genome g, using 'conf', the config file.
        net = neat.nn.FeedForwardNetwork.create(g, conf)

        nets.append(net)  # Adds each neural network 'net', to the list 'nets' containing the networks.
        g.fitness = 0  # Sets the initial fitness benchmark for each genome to 0.
        cars.append(Car())  # Add each car and the info it contains to the cars list.

    # Initialize and setup game / simulation test place.
    pygame.init()  # Load pygame.

    # Make sure that pygame only checks to see if the close button is clicked, no other button, or key
    # (saves processing time).
    pygame.event.set_allowed([pygame.QUIT, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP, pygame.MOUSEBUTTONDOWN])

    screen = pygame.display.set_mode((screen_width, screen_height))  # Sets up the display surface for the simulation.
    clock = pygame.time.Clock()  # Creates a proxy variable 'clock' to access the in-game clock.
    font = pygame.font.Font(os.path.join(misc_dir, 'Pixelar.ttf'),
                            20)  # Loads in a font 'Pixelar', with size 20 to the variable 'font'.

    level = pygame.image.load(
        os.path.join(image_dir, 'map3Flat.png')).convert_alpha()  # Loads in level to be  displayed to the var: 'level'.
    boundary = pygame.image.load(
        os.path.join(image_dir, 'BorderBB&W.png')).convert()  # Loads in a b&w image to help check for collisions.

    start_time = pygame.time.get_ticks()  # used to calculate elapsed time, for timer.
    tick = 60  # sets the amount of ticks that should be ticked each time the game is refreshed.
    global generation  # Using 'global' to access the variable 'generation' from outside this loop and function.

    # Each time all cars die or time limit passes, the while loop below is stopped, and it runs the code in run() again,
    # so it adds to the cars generation each time they all die.
    generation += 1

    # Main loop for running the simulation.
    while 1:
        pygame.event.pump()
        # Setup variables for the loop.
        remain_cars = 0  # Used to check how much cars are alive in total, initially set to 0.
        f_list = []  # A list used to see what car has the highest fitness, all cars fitness are added here and checked.
        m_speed = 0  # A variable used to display the speed of the car with the most fitness.
        m_acceleration = 0  # A variable used to display the acceleration amount of the car with the most fitness.
        m_steering = 0  # A variable used to display the turning angle of the car with the most fitness.
        m_position_x = 0  # A variable used to display the x-coordinate of the car with the most fitness.
        m_position_y = 0  # A variable used to display the y-coordinate of the car with the most fitness.
        m_fitness = 0  # A variable used to display the fitness level of the car with the most fitness.
        drawAll = False
        dt = clock.get_time() / 1000  # Variable used to calculate delta time.

        for event in pygame.event.get():  # Loop to check if anything that can be pressed was pressed:
            if event.type == pygame.QUIT:  # If the quit button was pressed:
                sys.exit(0)  # Exit the program.

        for index, car in enumerate(cars):  # For neural net ID, and car in the cars list,
            output = nets[index].activate(car.get_data())  # The output that the net 'returns' when given car data.
            i = output.index(max(output))  # i = the max output received from the net (the actual output).

            # Defining what the car does when it outputs certain values (accelerate, decelerate, brake, turn, etc..):
            if i == 0:
                car.accelerate(dt)
            elif i == 1:
                car.decelerate(dt)
            elif i == 2:
                car.brake(dt)

            if i == 3:
                car.turnLeft(dt)
            elif i == 4:
                car.turnRight(dt)

            if i ==5:
                car.blank1(dt)
            if i == 6:
                car.blank2(dt)
            if i == 7:
                car.blank1(dt)
                car.blank2(dt)
            # Update car acceleration and steering values.
            car.acceleration = max(-car.max_acceleration, min(car.acceleration, car.max_acceleration))
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
                    car.surface = car.surface.convert_alpha()  # Convert the cars image for faster calculations.

                    # Setting up the variables for statistics.
                    m_acceleration = car.acceleration  # This variable = the same as the best car.
                    m_steering = car.steering  # This variable = the same as the best car.
                    m_position_x = car.center[0]  # This variable = the same as the best car.
                    m_position_y = car.center[1]  # This variable = the same as the best car.
                    m_fitness = genomes[i][1].fitness
                    m_speed = (car.velocity[0] + car.velocity[1])  # This variable = the average speed of the best car.
                    m_speed = m_speed / 2

                    car.draw(screen)  # Draw this car (the best car) to the screen.

            elif car.get_alive() and drawAll:
                car.draw(screen)
            else:
                break  # Break out of this for loop.

        # Check if the generation should end.
        if pygame.time.get_ticks() >= 120000 * generation:  # if the ticks that passed is greater than 120k (120.s)*gen:
            break  # Exit the while loop and end the generation.

        if remain_cars == 0:  # If all cars died:
            break  # Exit the while loop and end the generation.

        # Setup generation timer.
        # Set the variable to be the same amount of elapsed ticks, divide it by 1k to get seconds, and divide it by
        # the generation amount to create a timer.
        gen_time = str((((pygame.time.get_ticks() - start_time) / 1000) / generation))

        # Convert the data to strings so it can be displayed.
        m_speed = str(m_speed)
        m_acceleration = str(m_acceleration)
        m_steering = str(m_steering)
        m_position_x = str(m_position_x)
        m_position_y = str(m_position_y)
        m_fitness = str("{:.2f}".format(m_fitness))

        #Draw FPS counter
        fps = str(int(clock.get_fps()))
        uiHandler.drawText(screen, 110, 760, font, 'FPS: ' + fps)

        # Draw a transparent box for stats to be written on.
        uiHandler.drawBox(screen, 200, 200, screen_width / 150, screen_height / 1.35)

        # Drawing the stats:
        uiHandler.drawText(screen, 110, 600, font, "Car generation: " + str(generation))

        uiHandler.drawText(screen, 110, 620, font, "Generation clock: " + gen_time[0:3] + "s")

        uiHandler.drawText(screen, 110, 640, font, "Speed: " + m_speed[0:4] + "mph")

        uiHandler.drawText(screen, 110, 660, font, "Throttle: " + m_acceleration[0:4])

        uiHandler.drawText(screen, 110, 680, font, "Steering: " + m_steering[0:4] + "°")

        uiHandler.drawText(screen, 110, 700, font, "Fitness: " + m_fitness[0:10])

        uiHandler.drawText(screen, 110, 720, font,
                           "Coordinates: " + "(" + str(m_position_x[0:4]) + ", " + str(m_position_y[0:3]) + ")")

        uiHandler.drawText(screen, 110, 740, font, "Remaining cars: " + str(remain_cars))

        pygame.display.flip()  # Refresh the entire screen (graphically).
        clock.tick_busy_loop(tick)  # Tick the clock by 'ticks' amount.
