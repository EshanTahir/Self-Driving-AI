# Import libraries.
import math  # For converting steering angle to degrees.
import os  # For file handling.
import random  # For random map spawn / reverse direction.
import sys  # To be used for closing the program.

import neat  # The genetic algorithm handler.
import pygame  # The game engine.

import Camera
import mapHandler
import renderHandler
from carHandler import Car
from paths import FONTS_DIR, IMAGES_DIR

screen_width = 1280  # Set program x resolution.
screen_height = 720  # Set program y resolution.
PHYSICS_DT = 1.0 / 60.0  # Fixed physics step so dt jitter doesn't mess up the car model.
MAX_FRAME_DT = 1.0 / 20.0  # Don't spiral if a frame hitches hard.

generation = -1  # Variable to count generations.

# Button control variables
draw_all = False  # A variable used to either display all cars or best car.
ai_view = False  # A variable used to show the x-ray / computer-vision view.

# Shared OpenGL renderer kept alive across generations.
shared_renderer = None


# Function to get (or create) the shared OpenGL renderer.
def get_renderer():
    global shared_renderer
    if shared_renderer is None:
        shared_renderer = renderHandler.Renderer(screen_width, screen_height)  # Create the window / renderer.
        try:
            icon = pygame.image.load(os.path.join(IMAGES_DIR, 'AI.png'))  # Load program icon.
            pygame.display.set_icon(icon)  # Set program icon.
        except pygame.error:
            pass
        pygame.display.set_caption('NEAT Driving Simulator')  # Set program title.
    return shared_renderer


# Function to update button label and rebuild cached text textures for the new string.
def set_button_text(button, text):
    button.text = text
    if hasattr(button, 'create_text_textures'):
        button.create_text_textures()


# Function called by NEAT each generation to run the driving simulation.
def run_car(genomes, conf):  # Genomes are the individual cars dna makeup, species are made up of similar genomes.
    global draw_all
    global ai_view
    global generation
    global shared_renderer

    pygame.init()  # Load pygame.

    # Make sure that pygame only checks for quit + mouse events
    # (saves processing time).
    pygame.event.set_allowed([
        pygame.QUIT, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP, pygame.MOUSEBUTTONDOWN
    ])

    # Reuse the shared OpenGL renderer (creates the window on first generation).
    renderer = get_renderer()

    clock = pygame.time.Clock()  # Creates a proxy variable 'clock' to access the in-game clock.
    font = pygame.font.Font(os.path.join(FONTS_DIR, 'Pixelar.ttf'), 24)  # Loads in a font 'Pixelar', with size 24.

    # Pick a random map / spawn / direction for this generation.
    maps = mapHandler.get_maps()
    rand_map = random.randrange(0, len(maps))
    rand_spawn = random.randrange(0, len(maps[rand_map][2]))

    map_real = maps[rand_map][0]  # Visual track image.
    map_border_surface = maps[rand_map][1]  # Border mask image (for x-ray + packing).
    # 2D uint8 mask (1 = driveable)  -  much faster than RGB array3d checks every ray.
    import numpy as np
    rgb = pygame.surfarray.array3d(map_border_surface)
    map_border = (rgb[:, :, 0] >= 250).astype(np.uint8)
    spawn_point = maps[rand_map][2][rand_spawn]
    checkpoints = maps[rand_map][3]
    reverse = random.random()

    # Pack map data passed into each Car instance.
    # [real_image, border_surface, spawn, checkpoints, reverse_roll]
    map_data = [map_real, map_border_surface, spawn_point, checkpoints, reverse]

    # Custom cursor images (normal + pressed).
    pygame.mouse.set_visible(False)
    cursors = [
        pygame.image.load(os.path.join(IMAGES_DIR, 'Cursor.png')).convert_alpha(),
        pygame.image.load(os.path.join(IMAGES_DIR, 'Cursor1.png')).convert_alpha(),
    ]
    cursor_state = 0
    cursor_img_rect = cursors[cursor_state].get_rect()
    cursor_texture_ids = [
        renderer.load_surface(cursors[0]),
        renderer.load_surface(cursors[1]),
    ]

    # Cache large map textures once instead of re-uploading every frame.
    map_real_texture_id = renderer.load_surface(map_real)
    map_border_texture_id = renderer.load_surface(map_border_surface)

    # UI buttons (OpenGL versions of the old pygame buttons) if the renderer has them.
    has_buttons = hasattr(renderer, 'Button')
    if has_buttons:
        skip_generation_button = renderer.Button(
            renderer, font, screen_width - 110, screen_height - 60, 100, 50, text='Skip Gen'
        )
        if draw_all:
            toggle_draw_all_button = renderer.Button(
                renderer, font, screen_width - 260, screen_height - 60, 140, 50, text='Draw Best'
            )
        else:
            toggle_draw_all_button = renderer.Button(
                renderer, font, screen_width - 260, screen_height - 60, 140, 50, text='Draw All'
            )

        if ai_view:
            toggle_ai_view_button = renderer.Button(
                renderer, font, screen_width - 410, screen_height - 60, 140, 50, text='Real View'
            )
        else:
            toggle_ai_view_button = renderer.Button(
                renderer, font, screen_width - 410, screen_height - 60, 140, 50, text='Computer Vision'
            )

    nets = []  # List to hold all the neural networks.
    cars = []  # List to hold all the cars and their data.
    camera = Camera.Camera_Group(screen_width, screen_height)

    # Create one network + car per genome.
    car_id = 0
    for c, g in genomes:  # c = each car or maybe amount of cars, g = each genome.
        # Use NEAT library to create each neural network, with genome g, using 'conf', the config file.
        net = neat.nn.FeedForwardNetwork.create(g, conf)
        nets.append(net)  # Adds each neural network 'net', to the list 'nets' containing the networks.
        g.fitness = 0  # Sets the initial fitness benchmark for each genome to 0.
        cars.append(Car(car_id, map_data))  # Add each car to the cars list.
        car_id += 1

    start_time = pygame.time.get_ticks()  # Used for the generation timer.
    tick = 60  # Target frames per second.
    cars_moved = False
    generation += 1  # Advance the generation counter.
    physics_accum = 0.0  # Accumulator for fixed-step physics.

    # Main simulation loop for this generation.
    while True:
        pygame.event.pump()

        # Setup variables for the loop.
        remain_cars = 0  # Used to check how much cars are alive in total, initially set to 0.
        v_list = []  # Velocities of alive cars (used for stall detection).
        f_list = []  # A list used to see what car has the highest fitness, all cars fitness are added here and checked.
        m_id = 0
        m_speed = 0  # A variable used to display the speed of the car with the most fitness.
        m_acceleration = 0  # A variable used to display the acceleration amount of the car with the most fitness.
        m_steering = 0  # A variable used to display the turning angle of the car with the most fitness.
        m_position_x = 0  # A variable used to display the x-coordinate of the car with the most fitness.
        m_position_y = 0  # A variable used to display the y-coordinate of the car with the most fitness.
        m_fitness = 0  # A variable used to display the fitness level of the car with the most fitness.

        # Real frame time (camera / render); physics uses a fixed step below.
        frame_dt = clock.get_time() / 1000.0  # Variable used to calculate delta time.
        if frame_dt <= 0:
            frame_dt = PHYSICS_DT
        frame_dt = min(frame_dt, MAX_FRAME_DT)
        physics_accum += frame_dt
        dt = frame_dt  # used by draw / camera

        # Event handling
        events = []
        for event in pygame.event.get():  # Loop to check if anything that can be pressed was pressed:
            if event.type == pygame.QUIT:  # If the quit button was pressed:
                # Shut down the shared renderer, then exit the whole program.
                renderer.cleanup()
                shared_renderer = None
                sys.exit(0)  # Exit the program.
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                cursor_state = 1
                events.append('left_mouse_button_down')
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                cursor_state = 0
                events.append('left_mouse_button_up')

        # Ask each living network for controls.
        for index, car in enumerate(cars):  # For neural net ID, and car in the cars list,
            if not car.get_alive():
                continue
            output = nets[index].activate(car.get_data())  # The output that the net 'returns' when given car data.

            # Prefer continuous 3-output nets; fall back to discrete max-index.
            if len(output) >= 3:
                throttle_output = output[0]
                brake_output = output[1]
                steering_output = output[2]
                commands = []

                if brake_output > 0.5:
                    commands.append('brake')
                elif throttle_output < -0.3:
                    commands.append('decelerate')
                elif throttle_output > 0.3:
                    commands.append('accelerate')

                if steering_output < -0.3:
                    commands.append('left')
                elif steering_output > 0.3:
                    commands.append('right')

                if hasattr(car, 'input'):
                    car.input(commands)
            else:
                i = output.index(max(output))
                if hasattr(car, 'input'):
                    commands = []
                    if i == 0:
                        commands.append('accelerate')
                    elif i == 1:
                        commands.append('decelerate')
                    elif i == 2:
                        commands.append('brake')
                    if i == 3:
                        commands.append('left')
                    elif i == 4:
                        commands.append('right')
                    car.input(commands)

        # Fixed-step physics.
        offset = camera.get_offset()
        while physics_accum >= PHYSICS_DT:
            for i, car in enumerate(cars):  # for each neural net, and car in cars list:
                if car.get_alive():  # if the car is alive:
                    car.update(map_border, [int(offset[0]), int(offset[1])], PHYSICS_DT)  # Update the cars position etc..
                    genomes[i][1].fitness += car.get_reward()  # Add the reward to the neural networks genomes fitness.
            physics_accum -= PHYSICS_DT

        for i, car in enumerate(cars):
            if car.get_alive():
                remain_cars += 1  # Add to the remaining cars number,
                f_list.append(genomes[i][1].fitness)  # Add each neural networks genomes fitness value to this list.
                v_list.append(car.velocity)

        # Drawing, and statistics.
        renderer.clear((10, 10, 10, 255))  # Clear the GPU frame.

        # Find the current best living car for camera follow + HUD stats.
        maximum_car_drawn = False
        best_index = None
        if f_list:
            best_fitness = max(f_list)
            for i, car in enumerate(cars):
                if car.get_alive() and genomes[i][1].fitness == best_fitness:
                    best_index = i
                    break

        if best_index is not None:
            best_car = cars[best_index]
            maximum_car_drawn = True
            m_id = best_car.id
            m_acceleration = getattr(best_car, 'throttle', best_car.acceleration)
            m_steering = best_car.steering
            # Prefer position; fall back to center from older cars.
            if hasattr(best_car, 'position'):
                m_position_x = best_car.position[0]
                m_position_y = best_car.position[1]
            else:
                m_position_x = best_car.center[0]
                m_position_y = best_car.center[1]
            m_fitness = genomes[best_index][1].fitness
            m_speed = best_car.speed

            # Follow the best car with the camera (smooth Camera if available).
            if hasattr(camera, 'center_target_camera'):
                try:
                    camera.center_target_camera(best_car, dt)
                except TypeError:
                    camera.center_target_camera(best_car)
            offset = camera.get_offset()
            ox, oy = offset[0], offset[1]

            if ai_view and hasattr(best_car, 'draw_ai'):
                # CV view  -  still uses car draw_ai if it talks to pygame; otherwise blit border.
                renderer.blit(map_border_texture_id, int(0 - ox), int(0 - oy))
            else:
                # Real view: track + car sprite via GPU blit of the map.
                renderer.blit(map_real_texture_id, int(0 - ox), int(0 - oy))

            # Draw best car (pygame-style draw still works onto a surface we upload if needed).
            # For this intermediate step we just show the map; car GPU draw arrives with later car layers.

        # Hit-test with a 1x1 rect at the mouse (cursor image is only for drawing).
        if has_buttons:
            cursor_hit = pygame.Rect(pygame.mouse.get_pos(), (1, 1))
            skip_generation_button.update(cursor_hit, events)
            toggle_draw_all_button.update(cursor_hit, events)
            toggle_ai_view_button.update(cursor_hit, events)

            skip_generation_button.active = True
            toggle_draw_all_button.active = True
            toggle_ai_view_button.active = True

            if toggle_ai_view_button.clicked_up:
                if ai_view:
                    ai_view = False
                    set_button_text(toggle_ai_view_button, 'Computer Vision')
                else:
                    ai_view = True
                    set_button_text(toggle_ai_view_button, 'Real View')

            if toggle_draw_all_button.clicked_up:
                if draw_all:
                    draw_all = False
                    set_button_text(toggle_draw_all_button, 'Draw All')
                else:
                    draw_all = True
                    set_button_text(toggle_draw_all_button, 'Draw Best')

        # Stall / end-of-generation checks (manual skip only  -  no auto-skip yet).
        now_tick = pygame.time.get_ticks()
        elapsed_ms = now_tick - start_time
        average_velocity = [0, 0]
        for i in v_list:
            average_velocity[0] += float(i[0])
            average_velocity[1] += float(i[1])
        try:
            average_velocity[0] /= len(v_list)
            average_velocity[1] /= len(v_list)
        except ZeroDivisionError:
            average_velocity = [0, 0]

        speed_mag = math.hypot(average_velocity[0], average_velocity[1])
        if speed_mag > 5:
            cars_moved = True  # At least some cars actually got going.

        user_skip = has_buttons and skip_generation_button.clicked_up
        if remain_cars == 0:
            print('--No cars left--' + '\n')
            break  # Breaks / exits out of the while loop.
        elif user_skip:
            print('--User skipped generation--' + '\n')
            break
        elif elapsed_ms >= 5000 and not cars_moved:
            print('--5 seconds passed cars not moving--' + '\n')
            break
        elif elapsed_ms >= 600000:
            print('--10 minutes passed, ending generation--' + '\n')
            break
        if not maximum_car_drawn:
            print("--Can't find best car--" + '\n')
            break

        # HUD panel + text.
        gen_time = '{:.1f}'.format(elapsed_ms / 1000)
        panel_x = screen_width / 150
        panel_y = screen_height / 1.35 - 20
        if hasattr(renderer, 'draw_rectangle'):
            renderer.draw_rectangle(panel_x, panel_y, 200, 200, '#000000', alpha=0.3)  # Semi-transparent HUD panel.
        if hasattr(renderer, 'draw_text'):
            hud_lines = [
                'Car Generation: ' + str(generation),
                'Generation Clock: ' + gen_time + 's',
                'Car ID: ' + str(m_id),
                'Speed: ' + '{:.0f}'.format(m_speed) + 'mph',
                'Throttle: ' + '{:.2f}'.format(m_acceleration),
                'Steering: ' + '{:.0f}'.format(m_steering) + '°',
                'Fitness: ' + '{:.0f}'.format(m_fitness),
                'Coordinates: (' + '{:.0f}'.format(m_position_x) + ', ' + '{:.0f}'.format(m_position_y) + ')',
                'Remaining Cars: ' + str(remain_cars),
                'FPS: ' + str(int(clock.get_fps())),
            ]
            text_x = panel_x + 10
            line_y = panel_y + 8
            line_h = 20
            for li, line in enumerate(hud_lines):
                renderer.draw_text(text_x, line_y + line_h * li, font, line, '#FFFFFF')  # Draw each HUD line.

        # Draw the custom cursor on top.
        cursor_img_rect.center = pygame.mouse.get_pos()
        cursor_tex = cursor_texture_ids[cursor_state]
        renderer.blit(cursor_tex, cursor_img_rect.x, cursor_img_rect.y)

        renderer.flip()  # Present the GPU frame.
        clock.tick(tick)  # Cap FPS.

    # Generation finished  -  free per-generation GPU resources (keep the window).
    renderer.unload_texture(map_real_texture_id)
    renderer.unload_texture(map_border_texture_id)
    for tex_id in cursor_texture_ids:
        renderer.unload_texture(tex_id)
    if has_buttons:
        skip_generation_button.cleanup()
        toggle_draw_all_button.cleanup()
        toggle_ai_view_button.cleanup()
