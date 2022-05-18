# Import libraries.
import os  # For file handling.
import random
import sys  # To be used for closing program.

import neat  # The genetic algorithm handler.
import pygame  # The game engine.

import uiHandler
from carHandler import Car
import mapHandler
import Camera

current_dir = os.path.dirname(os.path.abspath(__file__))  # Create var containing the current directory, for all OS.
image_dir = os.path.join(current_dir, 'Images')  # Create var containing the images directory, for all OS.
misc_dir = os.path.join(current_dir, 'Miscellaneous')  # Create var containing the misc directory, for all OS.

icon = pygame.image.load(os.path.join(image_dir, 'ai.png'))  # Load program icon.
pygame.display.set_icon(icon)  # Set program icon.
pygame.display.set_caption('NEAT Driving Simulator')  # Set program title.

screen_width = 1280  # Set program x resolution.
screen_height = 720  # set program y resolution.

generation = -1  # Variable to count generations.

#Button control variables
draw_all = False  # A variable used to either display all cars or best car.
ai_view = False


# Function to call on to run simulation
def run_car(genomes, conf):  # Genomes are the individual cars dna makeup, species are made up of similar genomes.
    # Initialize and setup game / simulation test place.
    pygame.init()  # Load pygame.

    # Make sure that pygame only checks to see if the close button is clicked, no other button, or key
    # (saves processing time).
    pygame.event.set_allowed([pygame.QUIT, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP, pygame.MOUSEBUTTONDOWN])

    screen = pygame.display.set_mode((screen_width, screen_height))  # Sets up the display surface for the simulation.
    clock = pygame.time.Clock()  # Creates a proxy variable 'clock' to access the in-game clock.
    font = pygame.font.Font(os.path.join(misc_dir, 'Pixelar.ttf'),
                            24)  # Loads in a font 'Pixelar', with size 20 to the variable 'font'.

    maps = mapHandler.get_maps()

    rand_map = random.randrange(0, len(maps))
    rand_spawn = random.randrange(0, len(maps[rand_map][2]))

    map_real = maps[rand_map][0]
    map_border = maps[rand_map][1]
    spawn_point = maps[rand_map][2][rand_spawn]
    checkpoints = maps[rand_map][3]

    reverse = random.random()

    map = [map_real, map_border, spawn_point, checkpoints, reverse]

    #Clear file
    f = open("Irend.txt", "w")
    f.write("")  # Fitness: {genomes[i][1].fitness} Generation: {generation}" + "\n")
    f.close()

    pygame.mouse.set_visible(False)
    cursors = [pygame.image.load(os.path.join(image_dir, 'Cursor.png')).convert_alpha(), pygame.image.load( os.path.join(image_dir, 'Cursor1.png')).convert_alpha()]
    cursor_state = 0
    cursor_img_rect = cursors[cursor_state].get_rect()

    global draw_all
    global ai_view
    cars_moved = False
    skip_generation_button = uiHandler.Button(font, 100, 50, screen_width-110, screen_height-60, text="Skip Gen")
    if draw_all:
        toggle_draw_all_button = uiHandler.Button(font, 140, 50, screen_width-260, screen_height-60, text="Draw Best")
    elif not draw_all:
        toggle_draw_all_button = uiHandler.Button(font, 140, 50, screen_width-260, screen_height-60, text="Draw All")

    if ai_view:
        toggle_ai_view_button = uiHandler.Button(font, 140, 50, screen_width - 410, screen_height - 60,
                                                 text="Real View")
    elif not ai_view:
        toggle_ai_view_button = uiHandler.Button(font, 140, 50, screen_width - 410, screen_height - 60,
                                                 text="Computer Vision")

    nets = []  # List to hold all the neural networks.
    cars = []  # List to hold all the cars and their data.
    camera_group = Camera.Camera_Group(map_real)

    car_id = 0
    for c, g in genomes:  # c = each car or maybe amount of cars, g = each genome.
        # Use NEAT library to create each neural network, with genome g, using 'conf', the config file.
        net = neat.nn.FeedForwardNetwork.create(g, conf)

        nets.append(net)  # Adds each neural network 'net', to the list 'nets' containing the networks.
        g.fitness = 0  # Sets the initial fitness benchmark for each genome to 0.
        cars.append(Car(car_id, map))  # Add each car and the info it contains to the cars list.
        car_id += 1

    for car in cars:
        camera_group.add(car)

    start_time = pygame.time.get_ticks()  # used to calculate elapsed time, for timer.
    tick = 24  # sets the amount of ticks that should be ticked each time the game is refreshed.
    global generation  # Using 'global' to access the variable 'generation' from outside this loop and function.

    # Each time all cars die or time limit passes, the while loop below is stopped, and it runs the code in run() again,
    # so it adds to the cars generation each time they all die.
    generation += 1

    # Main loop for running the simulation.
    while 1:
        pygame.event.pump()
        # Setup variables for the loop.
        remain_cars = 0  # Used to check how much cars are alive in total, initially set to 0.
        v_list = []
        f_list = []  # A list used to see what car has the highest fitness, all cars fitness are added here and checked.
        m_id = 0
        m_speed = 0  # A variable used to display the speed of the car with the most fitness.
        m_acceleration = 0  # A variable used to display the acceleration amount of the car with the most fitness.
        m_steering = 0  # A variable used to display the turning angle of the car with the most fitness.
        m_position_x = 0  # A variable used to display the x-coordinate of the car with the most fitness.
        m_position_y = 0  # A variable used to display the y-coordinate of the car with the most fitness.
        m_fitness = 0  # A variable used to display the fitness level of the car with the most fitness.
        write_output = True  # A variable used to output cars output values to file.
        dt = clock.get_time() / 1000  # Variable used to calculate delta time.

        #Event handling
        events = []
        for event in pygame.event.get():  # Loop to check if anything that can be pressed was pressed:
            if event.type == pygame.QUIT:  # If the quit button was pressed:
                sys.exit(0)  # Exit the program.
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                cursor_state = 1
                events.append("left_mouse_button_down")
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                cursor_state = 0
                events.append("left_mouse_button_up")


        for index, car in enumerate(cars):  # For neural net ID, and car in the cars list,
            output = nets[index].activate(car.get_data())  # The output that the net 'returns' when given car data.
            i = output.index(max(output))  # i = the max output received from the net (the actual output).

            # Used to output the cars outputs to file "Irend.txt".
            if write_output:
                f = open("Irend.txt", "a")
                f.write(f"Output: {str(i)}"+"\n")# Fitness: {genomes[i][1].fitness} Generation: {generation}" + "\n")
                f.close()

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
            elif i == 5:
                car.blank1(dt)
            '''
            pressed = pygame.key.get_pressed()

            if pressed[pygame.K_UP]:
                car.accelerate(dt)
            elif pressed[pygame.K_DOWN]:
                car.decelerate(dt)
            elif pressed[pygame.K_SPACE]:
                car.brake(dt)

            if pressed[pygame.K_LEFT]:
                car.turnLeft(dt)
            elif pressed[pygame.K_RIGHT]:
                car.turnRight(dt)'''
            # Update car acceleration and steering values.
            car.acceleration = max(-car.max_acceleration, min(car.acceleration, car.max_acceleration))
            car.steering = max(-car.max_steering, min(car.steering, car.max_steering))

        for i, car in enumerate(cars):  # for each neural net, and car in cars list:
            if car.get_alive():  # if the car is alive:
                remain_cars += 1  # Add to the remaining cars number,
                car.update(map_border, [int(camera_group.get_offset()[0]), int(camera_group.get_offset()[0])], dt)  # Update the cars position etc..
                genomes[i][1].fitness += car.get_reward()  # Add the reward to the neural networks genomes fitness.
                f_list.append(genomes[i][1].fitness)  # Add each neural networks genomes fitness value to this list.
                f_list.sort()  # Sort all the fitness values (ascending) in this list.

                v_list.append(car.velocity)

        # Drawing, and statistics.
        maximum_car_drawn = False
        for i, car in enumerate(cars):  # for each cars neural network and car in the cars list:
            if car.get_alive() and not draw_all:  # if that car is alive:
                if genomes[i][1].fitness == max(f_list) and not maximum_car_drawn:  # If the neural networks genomes fitness is the highest and it wasnt already drawn this frame:
                    maximum_car_drawn = True
                    car.surface = car.surface.convert_alpha()  # Convert the cars image for faster calculations.

                    # Setting up the variables for statistics.
                    m_id = car.id
                    m_acceleration = car.acceleration  # This variable = the same as the best car.
                    m_steering = car.steering  # This variable = the same as the best car.
                    m_position_x = car.center[0]  # This variable = the same as the best car.
                    m_position_y = car.center[1]  # This variable = the same as the best car.
                    m_fitness = genomes[i][1].fitness
                    m_speed = car.speed

                    offset = camera_group.get_offset()
                    if ai_view:
                        car.draw_ai(screen, camera_group.get_offset(), font)
                        camera_group.individual_draw(car, False, False)
                    else:
                        camera_group.individual_draw(car, True, False)
                        car.draw(screen, offset, False)

            elif car.get_alive() and draw_all:
                car.draw_ai(screen, camera_group.get_offset(), font)
                if genomes[i][1].fitness == max(f_list):
                    camera_group.custom_draw(car, False, False)
            else:
                break  # Break out of this for loop.

        #Buttons
        skip_generation_button.update(screen, cursor_img_rect, events)
        toggle_draw_all_button.update(screen, cursor_img_rect, events)
        toggle_ai_view_button.update(screen, cursor_img_rect, events)

        skip_generation_button.active = True
        toggle_draw_all_button.active = True

        if not draw_all:
            toggle_ai_view_button.active = True
        elif draw_all:
            toggle_ai_view_button.active = False

        if toggle_ai_view_button.clicked_up:
            if ai_view:
                ai_view = False
                toggle_ai_view_button.text = "Computer Vision"
            elif not ai_view:
                toggle_ai_view_button.text = "Real View"
                ai_view = True

        if toggle_draw_all_button.clicked_up:
            if draw_all:
                toggle_draw_all_button.text = "Draw All"
                draw_all = False
            elif not draw_all:
                toggle_draw_all_button.text = "Draw Best"
                draw_all = True

        # Check if the generation should end.
        average_velocity = [0,0]
        for i in v_list:
            average_velocity[0] += float(i[0])
            average_velocity[1] += float(i[1])
        try:
            average_velocity[0] /= len(v_list)
            average_velocity[1] /= len(v_list)
        except:
            average_velocity = [0, 0]

        if average_velocity[0] >= 0 or average_velocity[1] >= 0:
            cars_moved = True

        if remain_cars == 0:  # If all cars died:
            print("--No cars left--"+"\n")
            break  # Exit the while loop and end the generation.

        elif skip_generation_button.clicked_up: #Manually skip generation
            print("--User skipped generation--"+"\n")
            break  # Exit the while loop and end the generation.

        elif pygame.time.get_ticks() >= 5000*generation and not cars_moved:  # if the ticks that passed is greater than 5k (5.s) and cars havent moved:
            print("--5 seconds passed cars not moving-+"+"\n")
            break  # Exit the while loop and end the generation.

        elif remain_cars <= 16 and average_velocity[0] == 0 and average_velocity[1] == 0:
            print(f"--{remain_cars} car(s) arent moving-+"+"\n")
            break  # Exit the while loop and end the generation.

        if pygame.time.get_ticks() >= 600000*generation:
            print("--10 minutes passed, ending generation-+"+"\n")
            break
        if not maximum_car_drawn:
            print("--Can't find best car-+"+"\n")
            break
        # Setup generation timer.
        # Set the variable to be the same amount of elapsed ticks, divide it by 1k to get seconds, and divide it by
        # the generation amount to create a timer. Edit format to 2 decimal places.
        gen_time = (((pygame.time.get_ticks() - start_time) / 1000))
        gen_time = str("{:.2f}".format(gen_time))

        # Convert the data to strings and format them to 2 decimal places so it can be displayed.
        m_id = str(m_id)
        m_speed = str("{:.2f}".format(m_speed))
        m_acceleration = str("{:.2f}".format(m_acceleration))
        m_steering = str("{:.2f}".format(m_steering))
        m_position_x = str("{:.0f}".format(m_position_x))
        m_position_y = str("{:.0f}".format(m_position_y))
        m_fitness = str("{:.2f}".format(m_fitness))


        # Draw a transparent box for stats to be written on.
        uiHandler.draw_rectangle(screen, 200, 200, screen_width / 150, screen_height / 1.35 - 20, transparent=True, alpha=75, rgb=("#000000"))

        # Drawing the stats:
        uiHandler.draw_text(screen, screen_width / 150+100, -20+screen_height / 1.35+7 + 20*0, font, "Car Generation: " + str(generation),rgb=("#FFFFFF"))

        uiHandler.draw_text(screen, screen_width / 150+100, -20+screen_height / 1.35+7 + 20*1, font, "Generation Clock: " + gen_time + "s",rgb=("#FFFFFF"))

        uiHandler.draw_text(screen, screen_width / 150+100, screen_height / 1.35+7 + 20*1, font, "Car ID: " + m_id,rgb=("#FFFFFF"))

        uiHandler.draw_text(screen, screen_width / 150+100, screen_height / 1.35+7 + 20*2, font, "Speed: " + m_speed + "mph",rgb=("#FFFFFF"))

        uiHandler.draw_text(screen, screen_width / 150+100, screen_height / 1.35+7 + 20*3, font, "Throttle: " + m_acceleration,rgb=("#FFFFFF"))

        uiHandler.draw_text(screen, screen_width / 150+100, screen_height / 1.35+7 + 20*4, font, "Steering: " + m_steering + "°",rgb=("#FFFFFF"))

        uiHandler.draw_text(screen, screen_width / 150+100, screen_height / 1.35+7 + 20*5, font, "Fitness: " + m_fitness,rgb=("#FFFFFF"))

        uiHandler.draw_text(screen, screen_width / 150+100, screen_height / 1.35+7 + 20*6, font,
                           "Coordinates: " + "(" + str(m_position_x) + ", " + str(m_position_y) + ")",rgb=("#FFFFFF"))

        uiHandler.draw_text(screen, screen_width / 150+100, screen_height / 1.35+7+20*7, font, "Remaining Cars: " + str(remain_cars),rgb=("#FFFFFF"))

        # Draw FPS counter
        fps = str(int(clock.get_fps()))
        uiHandler.draw_text(screen, screen_width / 150+100, screen_height / 1.35+7+20*8, font, 'FPS: ' + fps,rgb=("#FFFFFF"))

        cursor_img_rect.center = pygame.mouse.get_pos()
        screen.blit(cursors[cursor_state], cursor_img_rect)

        pygame.display.flip()  # Refresh the entire screen (graphically).
        clock.tick_busy_loop(tick)  # Tick the clock by 'ticks' amount.
