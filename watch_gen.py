# Watch PPO on procedurally generated black/white loop tracks.
#
#   python watch_gen.py
#   python watch_gen.py --seed 106
#
# Controls (same as watch_ppo, plus):
#   N           next random track
#   P           previous seed
#   R           reset car on same track
#   G           reshuffle width a bit + new track

# Import libraries.
import argparse  # For reading command line flags.
import glob  # To search for saved model zips.
import math  # For angle wrapping when interpolating rotation.
import os  # For paths.
import sys  # So we can add src/ onto the import path / exit.

ROOT = os.path.dirname(os.path.abspath(__file__))  # Folder this script lives in.
sys.path.insert(0, os.path.join(ROOT, 'src'))  # Let us import stuff from src/.


# Function to find the newest ppo_final.zip under runs/.
def find_model():
    finals = glob.glob(os.path.join(ROOT, 'runs', '**', 'ppo_final.zip'), recursive=True)
    if finals:
        finals.sort(key=os.path.getmtime, reverse=True)
        return finals[0]
    return None


# Function to open a window and watch the policy on generated tracks.
def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', default=None)
    p.add_argument('--seed', type=int, default=100)
    p.add_argument('--width', type=int, default=70)
    p.add_argument('--difficulty', default='hard', choices=['easy', 'medium', 'hard'])
    args = p.parse_args()

    model_path = args.model or find_model()
    if not model_path or not os.path.isfile(model_path):
        print('No model found.')
        sys.exit(1)

    print('Loading ' + str(model_path) + ' ...')

    import numpy as np
    import pygame
    from stable_baselines3 import PPO

    import renderHandler
    from Camera import Camera_Group
    from carHandler import Car
    from paths import FONTS_DIR
    from rl.env import ACTION_REPEAT, PHYSICS_DT, make_border_mask
    from rl.trackgen import generate_loop_track

    # Make sure we get a real display (train scripts set SDL to dummy).
    os.environ.pop('SDL_VIDEODRIVER', None)
    if pygame.get_init():
        try:
            pygame.display.quit()
        except pygame.error:
            pass
    pygame.init()
    pygame.font.init()

    model = PPO.load(model_path, device='cpu')
    obs_n = int(model.observation_space.shape[0])
    print('Model loaded (obs=' + str(obs_n) + '). Opening window...')

    # Function to build an observation that matches the checkpoint's size.
    def obs_for_model():
        raw = np.asarray(car.get_data(), dtype=np.float32)
        if raw.shape[0] == obs_n:
            return raw
        if raw.shape[0] > obs_n:
            return raw[:obs_n]
        out = np.zeros(obs_n, dtype=np.float32)
        out[: raw.shape[0]] = raw
        return out

    screen_w, screen_h = 1280, 720
    renderer = renderHandler.Renderer(screen_w, screen_h, vsync=True)
    pygame.display.set_caption('PPO gen tracks - N next, P prev, R reset, Esc quit')
    font = pygame.font.Font(os.path.join(FONTS_DIR, 'Pixelar.ttf'), 26)
    clock = pygame.time.Clock()
    camera = Camera_Group(screen_w, screen_h, smooth_factor=0.12, look_ahead=0.28)

    track_seed = int(args.seed)  # Current procedural track seed.
    road_width = int(args.width)  # Half-width of the road in pixels.
    difficulty = args.difficulty
    map_tex = border_tex = None  # GPU textures for the current track.
    mask = None  # Collision mask for the current track.
    pack = None  # Current map pack from generate_loop_track.

    follow_cam = True
    ai_view = False
    show_radar = True
    show_cps = True  # Draw checkpoint markers on the real view.
    paused = False
    pan_speed = 420.0
    dragging = False
    drag_last = (0, 0)
    speed_steps = [0.1, 0.25, 0.5, 1.0, 1.5, 2.0]
    speed_i = 3  # 1.0x
    physics_accum = 0.0
    watch_action_repeat = max(1, ACTION_REPEAT // 2)
    hold_throttle = hold_brake = hold_steer = 0.0
    target_throttle = target_brake = target_steer = 0.0
    ticks_since_decision = watch_action_repeat
    car = None

    # Function to make a car on a given map_data list.
    def make_car(map_data):
        c = Car(0, map_data, renderer=renderer, sprite_config='BlueCar.png')
        c.radar_period = 1  # Refresh rays every tick for smooth CV lines.
        return c

    # Function to generate / load a track and spawn a car on it.
    def load_track(seed, width):
        nonlocal pack, mask, map_tex, border_tex, car, physics_accum, ticks_since_decision
        if car is not None:
            car.cleanup()  # Free the old car first.
        if map_tex is not None:
            renderer.unload_texture(map_tex)
        if border_tex is not None:
            renderer.unload_texture(border_tex)

        pack = generate_loop_track(
            seed=seed, road_half_width=width, difficulty=difficulty
        )
        mask = make_border_mask(pack[1])
        map_tex = renderer.load_surface(pack[0])
        border_tex = renderer.load_surface(pack[1])
        spawn = pack[2][0]
        map_data = [pack[0], pack[1], spawn, pack[3], 0.0]
        car = make_car(map_data)
        physics_accum = 0.0
        ticks_since_decision = watch_action_repeat
        camera.initialized = False
        camera.snap_to(car.position.x, car.position.y)
        print(
            'Track seed=' + str(seed) + '  width=' + str(width)
            + '  diff=' + str(difficulty) + '  cps=' + str(len(pack[3]))
        )

    # Function to reset the car on the same track (same spawn).
    def reset_car():
        nonlocal car, physics_accum, ticks_since_decision
        car.cleanup()
        spawn = pack[2][0]
        map_data = [pack[0], pack[1], spawn, pack[3], 0.0]
        car = make_car(map_data)
        physics_accum = 0.0
        ticks_since_decision = watch_action_repeat
        if follow_cam:
            camera.initialized = False

    load_track(track_seed, road_width)
    print('N next track | P prev | G new width | R reset | same cam/slow-mo keys as watch_ppo')

    running = True
    while running:
        dt = clock.get_time() / 1000.0 or PHYSICS_DT
        sim_speed = speed_steps[speed_i]
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_n:
                    track_seed += 1  # Next seed.
                    load_track(track_seed, road_width)
                elif event.key == pygame.K_p:
                    track_seed = max(0, track_seed - 1)  # Previous seed.
                    load_track(track_seed, road_width)
                elif event.key == pygame.K_g:
                    # Reshuffle difficulty + width a bit, then jump to a new seed.
                    import random
                    difficulty = random.choice(['easy', 'medium', 'hard'])
                    if difficulty == 'hard':
                        road_width = int(random.choice([40, 48, 55]))
                    else:
                        road_width = int(random.choice([55, 65, 70, 80, 95]))
                    track_seed += 17
                    load_track(track_seed, road_width)
                elif event.key == pygame.K_1:
                    difficulty = 'easy'
                    load_track(track_seed, road_width)
                elif event.key == pygame.K_2:
                    difficulty = 'medium'
                    load_track(track_seed, road_width)
                elif event.key == pygame.K_3:
                    difficulty = 'hard'
                    load_track(track_seed, road_width)
                elif event.key == pygame.K_r:
                    reset_car()
                elif event.key == pygame.K_v:
                    ai_view = not ai_view
                elif event.key == pygame.K_c:
                    follow_cam = not follow_cam
                    if follow_cam:
                        camera.snap_to(car.position.x, car.position.y)
                elif event.key == pygame.K_f:
                    show_radar = not show_radar
                elif event.key == pygame.K_h:
                    show_cps = not show_cps  # Toggle checkpoint markers.
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_LEFTBRACKET):
                    speed_i = max(0, speed_i - 1)
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_RIGHTBRACKET):
                    speed_i = min(len(speed_steps) - 1, speed_i + 1)
                elif event.key in (pygame.K_0, pygame.K_KP0):
                    speed_i = speed_steps.index(1.0)
            elif event.type == pygame.MOUSEWHEEL:
                mods = pygame.key.get_mods()
                if mods & pygame.KMOD_SHIFT:
                    speed_i = min(len(speed_steps) - 1, speed_i + 1) if event.y > 0 else max(0, speed_i - 1)
                else:
                    pan_speed = max(80.0, min(1600.0, pan_speed * (1.15 if event.y > 0 else 1 / 1.15)))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                dragging = True
                drag_last = event.pos
                follow_cam = False
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
                dragging = False
            elif event.type == pygame.MOUSEMOTION and dragging:
                camera.pan(drag_last[0] - event.pos[0], drag_last[1] - event.pos[1])
                drag_last = event.pos

        # Free-cam WASD / arrow pan.
        keys = pygame.key.get_pressed()
        if not follow_cam:
            move = pan_speed * dt
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                camera.pan(-move, 0)
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                camera.pan(move, 0)
            if keys[pygame.K_w] or keys[pygame.K_UP]:
                camera.pan(0, -move)
            if keys[pygame.K_s] or keys[pygame.K_DOWN]:
                camera.pan(0, move)

        # If the car died, respawn on the same track.
        if not car.get_alive():
            reset_car()

        # Fixed-step physics + leftover alpha for smooth in-between renders.
        prev_pos = pygame.Vector2(car.position)
        prev_rot = float(car.rotation)
        if not paused:
            physics_accum += min(dt, 0.05) * sim_speed
            steps = 0
            while physics_accum >= PHYSICS_DT and steps < 8:
                if not car.get_alive():
                    break  # Breaks / exits out of the physics loop.
                prev_pos = pygame.Vector2(car.position)
                prev_rot = float(car.rotation)
                if ticks_since_decision >= watch_action_repeat:
                    action, _ = model.predict(obs_for_model(), deterministic=True)
                    target_throttle, target_brake, target_steer = map(float, action)
                    ticks_since_decision = 0
                # Ease inputs toward policy targets so steering isn't jumpy.
                blend = 0.45
                hold_throttle += (target_throttle - hold_throttle) * blend
                hold_brake += (target_brake - hold_brake) * blend
                hold_steer += (target_steer - hold_steer) * blend
                car.apply_continuous(hold_throttle, hold_brake, hold_steer)
                car.update(mask, [0, 0], PHYSICS_DT)
                ticks_since_decision += 1
                physics_accum -= PHYSICS_DT
                steps += 1
            if physics_accum > PHYSICS_DT * 4:
                physics_accum = 0.0

        alpha = 0.0 if paused else max(0.0, min(1.0, physics_accum / PHYSICS_DT))
        render_pos = prev_pos.lerp(pygame.Vector2(car.position), alpha)
        drot = (car.rotation - prev_rot + math.pi) % (2 * math.pi) - math.pi
        render_rot = prev_rot + drot * alpha

        # Temporarily park car at interpolated pose for draw / camera.
        real_pos = pygame.Vector2(car.position)
        real_rot = float(car.rotation)
        car.position.update(render_pos)
        car.rotation = render_rot
        car.corners = car.get_corners()

        if follow_cam:
            camera.center_target_camera(car, dt)
        offset = camera.get_offset()

        renderer.clear((8, 8, 10, 255))
        if not paused:
            car.update_skid_marks(dt)
        if ai_view:
            car.draw_ai(
                offset, font,
                border_texture_id=border_tex,
                draw_radar=show_radar,
            )
        else:
            renderer.blit(map_tex, -offset[0], -offset[1])
            # Draw checkpoint dots if that toggle is on.
            if show_cps:
                for i, cp in enumerate(pack[3]):
                    color = '#4060FF' if i != car.current_checkpoint % len(pack[3]) else '#FFCC00'
                    renderer.draw_circle(cp[0] - offset[0], cp[1] - offset[1], 10, color)
            car.draw(dt, offset, draw_radar=show_radar, draw_skid=True, draw_wheels=True)

        # Put the real physics pose back.
        car.position.update(real_pos)
        car.rotation = real_rot
        car.corners = car.get_corners()

        cps = car.checkpoints_completed
        pause_s = ' PAUSE' if paused else ''
        view_s = 'CV' if ai_view else 'REAL'
        hud = (
            'GEN ' + str(difficulty) + ' seed=' + str(track_seed) + ' w=' + str(road_width)
            + '  ' + '{:g}'.format(sim_speed) + 'x' + pause_s + '  ' + view_s
            + '  spd ' + '{:.0f}'.format(car.speed) + '  cp ' + str(cps)
        )
        help_s = 'N/P track  1/2/3 diff  G random  H CPs  R reset  -/= slow-mo  Esc'
        renderer.draw_rectangle(8, 8, 1100, 52, '#000000', alpha=0.5)
        renderer.draw_text(16, 14, font, hud, '#FFFFFF')
        renderer.draw_text(16, 36, font, help_s, '#BBBBBB')
        renderer.flip()
        clock.tick(60)

    # Cleanup when we leave the loop.
    if car is not None:
        car.cleanup()
    if map_tex is not None:
        renderer.unload_texture(map_tex)
    if border_tex is not None:
        renderer.unload_texture(border_tex)
    renderer.cleanup()


if __name__ == '__main__':
    main()
