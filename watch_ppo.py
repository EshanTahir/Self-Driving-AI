# Watch a trained PPO policy with the OpenGL sim camera.
#
#   python watch_ppo.py
#   python watch_ppo.py --model runs/ppo/ppo_final.zip
#
# Controls:
#   R           reset car
#   V           real view / computer vision (x-ray)
#   C           follow cam / free cam
#   WASD/Arrows pan (free cam)
#   RMB drag    pan (free cam)
#   Wheel       pan speed (free cam)
#   F           toggle radar
#   Space       pause
# - / =       slower / faster (slow-mo)
#   0           reset speed to 1x
#   Esc / Q     quit

# Import libraries.
import argparse  # For reading command line flags.
import glob  # To search for saved model zips.
import math  # For angle wrapping when interpolating rotation.
import os  # For paths.
import sys  # So we can add src/ onto the import path / exit.

ROOT = os.path.dirname(os.path.abspath(__file__))  # Folder this script lives in.
sys.path.insert(0, os.path.join(ROOT, 'src'))  # Let us import stuff from src/.


# Function to find a model zip under runs/ (prefer newest ppo_final.zip).
def find_model():
    # Prefer newest final, then any newest zip under runs/.
    finals = glob.glob(os.path.join(ROOT, 'runs', '**', 'ppo_final.zip'), recursive=True)
    if finals:
        finals.sort(key=os.path.getmtime, reverse=True)
        return finals[0]
    found = glob.glob(os.path.join(ROOT, 'runs', '**', '*.zip'), recursive=True)
    if found:
        found.sort(key=os.path.getmtime, reverse=True)
        return found[0]
    return None


# Function to open a window and watch the trained policy drive.
def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', default=None, help='Path to SB3 .zip (default: newest under runs/)')
    args = p.parse_args()

    model_path = args.model or find_model()
    if not model_path or not os.path.isfile(model_path):
        print('No trained model found.')
        print('  python train_ppo.py --steps 100000 --n-envs 4')
        print('  python watch_ppo.py')
        sys.exit(1)

    print('Loading ' + str(model_path) + ' ...')

    import numpy as np
    import pygame
    from stable_baselines3 import PPO

    import mapHandler
    import renderHandler
    from Camera import Camera_Group
    from carHandler import Car
    from paths import FONTS_DIR
    from rl.env import ACTION_REPEAT, PHYSICS_DT, make_border_mask

    # Make sure we get a real display (train scripts set SDL to dummy).
    os.environ.pop('SDL_VIDEODRIVER', None)
    if pygame.get_init():
        try:
            pygame.display.quit()  # Drop any leftover headless display.
        except pygame.error:
            pass
    pygame.init()
    pygame.font.init()

    model = PPO.load(model_path, device='cpu')
    obs_n = int(model.observation_space.shape[0])  # How many floats this checkpoint expects.
    print('Model loaded (obs=' + str(obs_n) + '). Opening window...')

    # Function to build an observation that matches the checkpoint's size.
    # Older models want 16 floats, newer ones want 19 - trim or pad as needed.
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
    pygame.display.set_caption('PPO watch - -/= slow-mo, V view, C cam, Space pause')
    font = pygame.font.Font(os.path.join(FONTS_DIR, 'Pixelar.ttf'), 26)
    clock = pygame.time.Clock()
    # Softer follow so the view doesn't stutter with physics ticks.
    camera = Camera_Group(screen_w, screen_h, smooth_factor=0.12, look_ahead=0.28)

    maps = mapHandler.get_maps()
    m = maps[0]  # Use map_3 (first map) for watching.
    mask = make_border_mask(m[1])  # Collision mask from the border image.
    map_tex = renderer.load_surface(m[0])  # Visual map texture.
    border_tex = renderer.load_surface(m[1])  # Border texture for CV / x-ray view.

    follow_cam = True  # Start following the car.
    ai_view = False  # Real view vs computer vision.
    show_radar = True  # Draw radar lines or not.
    paused = False
    pan_speed = 420.0  # How fast free-cam pans with WASD.
    dragging = False  # True while right-mouse is held for panning.
    drag_last = (0, 0)  # Last mouse pos while dragging.
    # Playback rate: 1.0 = realtime, 0.25 = quarter-speed slow-mo, etc.
    speed_steps = [0.1, 0.25, 0.5, 1.0, 1.5, 2.0]
    speed_i = 3  # Index of 1.0x in speed_steps.
    physics_accum = 0.0  # Leftover time waiting for the next physics tick.
    # Watch uses denser decisions + action easing so steering doesn't hitch.
    watch_action_repeat = max(1, ACTION_REPEAT // 2)
    hold_throttle = hold_brake = hold_steer = 0.0  # Current eased controls.
    target_throttle = target_brake = target_steer = 0.0  # What the policy last asked for.
    ticks_since_decision = watch_action_repeat  # Force a decision on the first tick.
    # Pose before last physics step - used to interpolate render between ticks.
    render_pos = None
    render_rot = None

    # Function to spawn a fresh car at the map's first spawn point.
    def new_car():
        spawn = m[2][0]
        map_data = [m[0], m[1], spawn, m[3], 0.0]
        c = Car(0, map_data, renderer=renderer, sprite_config='BlueCar.png')
        c.radar_period = 1  # Refresh rays every tick for smooth CV lines.
        return c

    car = new_car()
    render_pos = pygame.Vector2(car.position)
    render_rot = float(car.rotation)
    print('Controls: -/= slow-mo | 0 =1x | V view | C cam | Space pause | R reset')
    running = True
    while running:
        dt = clock.get_time() / 1000.0 or PHYSICS_DT  # Seconds since last frame.
        sim_speed = speed_steps[speed_i]  # Current playback multiplier.
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False  # Quit.
                elif event.key == pygame.K_r:
                    # Reset the car on the same map.
                    car.cleanup()
                    car = new_car()
                    physics_accum = 0.0
                    ticks_since_decision = ACTION_REPEAT
                    if follow_cam:
                        camera.initialized = False  # Snap follow cam back onto the car.
                elif event.key == pygame.K_v:
                    ai_view = not ai_view  # Toggle real / CV view.
                elif event.key == pygame.K_c:
                    follow_cam = not follow_cam  # Toggle follow / free cam.
                    if follow_cam:
                        camera.snap_to(car.position.x, car.position.y)
                elif event.key == pygame.K_f:
                    show_radar = not show_radar  # Toggle radar drawing.
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_LEFTBRACKET):
                    speed_i = max(0, speed_i - 1)  # Slower.
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_RIGHTBRACKET):
                    speed_i = min(len(speed_steps) - 1, speed_i + 1)  # Faster.
                elif event.key == pygame.K_0 or event.key == pygame.K_KP0:
                    speed_i = speed_steps.index(1.0)  # Back to 1x.
            elif event.type == pygame.MOUSEWHEEL:
                # Shift+wheel = playback speed; plain wheel = free-cam pan speed.
                mods = pygame.key.get_mods()
                if mods & pygame.KMOD_SHIFT:
                    if event.y > 0:
                        speed_i = min(len(speed_steps) - 1, speed_i + 1)
                    else:
                        speed_i = max(0, speed_i - 1)
                else:
                    pan_speed = max(80.0, min(1600.0, pan_speed * (1.15 if event.y > 0 else 1 / 1.15)))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                dragging = True  # Start free-cam drag with right mouse.
                drag_last = event.pos
                follow_cam = False
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
                dragging = False
            elif event.type == pygame.MOUSEMOTION and dragging:
                dx = drag_last[0] - event.pos[0]
                dy = drag_last[1] - event.pos[1]
                camera.pan(dx, dy)
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

        # If the car died, respawn automatically.
        if not car.get_alive():
            car.cleanup()
            car = new_car()
            physics_accum = 0.0
            ticks_since_decision = ACTION_REPEAT
            if follow_cam:
                camera.initialized = False

        # Fixed-step physics + leftover alpha for smooth in-between renders.
        prev_pos = pygame.Vector2(car.position)
        prev_rot = float(car.rotation)
        if not paused:
            physics_accum += min(dt, 0.05) * sim_speed  # Cap dt so we don't spiral.
            steps = 0
            while physics_accum >= PHYSICS_DT and steps < 8:
                if not car.get_alive():
                    break  # Breaks / exits out of the physics loop.
                prev_pos = pygame.Vector2(car.position)  # Remember pose before this tick.
                prev_rot = float(car.rotation)
                # Ask the policy for a new action every watch_action_repeat ticks.
                if ticks_since_decision >= watch_action_repeat:
                    action, _ = model.predict(obs_for_model(), deterministic=True)
                    target_throttle, target_brake, target_steer = map(float, action)
                    ticks_since_decision = 0
                # Ease inputs toward policy targets (cuts choppy steer flips).
                blend = 0.45
                hold_throttle += (target_throttle - hold_throttle) * blend
                hold_brake += (target_brake - hold_brake) * blend
                hold_steer += (target_steer - hold_steer) * blend
                car.apply_continuous(hold_throttle, hold_brake, hold_steer)
                car.update(mask, [0, 0], PHYSICS_DT)
                ticks_since_decision += 1
                physics_accum -= PHYSICS_DT
                steps += 1
            # If we fell way behind, just drop the leftover time.
            if physics_accum > PHYSICS_DT * 4:
                physics_accum = 0.0

        # Blend between prev and current pose for smoother drawing.
        alpha = 0.0 if paused else max(0.0, min(1.0, physics_accum / PHYSICS_DT))
        render_pos = prev_pos.lerp(pygame.Vector2(car.position), alpha)
        # Shortest-path angle lerp so we don't spin the long way around.
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

        renderer.clear((10, 10, 10, 255))
        if not paused:
            car.update_skid_marks(dt)
        if ai_view:
            # Computer vision / x-ray style draw.
            car.draw_ai(
                offset, font,
                border_texture_id=border_tex,
                draw_radar=show_radar,
            )
        else:
            # Normal colored map + car.
            renderer.blit(map_tex, -offset[0], -offset[1])
            car.draw(
                dt, offset,
                draw_radar=show_radar,
                draw_skid=True,
                draw_wheels=True,
            )

        # Put the real physics pose back so the next tick is correct.
        car.position.update(real_pos)
        car.rotation = real_rot
        car.corners = car.get_corners()

        # HUD text in the top-left.
        cps = car.checkpoints_completed
        mode = 'CV' if ai_view else 'REAL'
        cam = 'FOLLOW' if follow_cam else 'FREE(' + '{:.0f}'.format(pan_speed) + ')'
        pause_s = ' PAUSE' if paused else ''
        radar_s = 'ON' if show_radar else 'OFF'
        hud = (
            '{:g}'.format(sim_speed) + 'x' + pause_s + '  ' + mode + '  ' + cam
            + '  radar=' + radar_s + '  spd ' + '{:.0f}'.format(car.speed) + '  cp ' + str(cps)
        )
        help_s = '-/= or Shift+wheel speed  0=1x  V view  C cam  Space pause  R reset'
        renderer.draw_rectangle(8, 8, 980, 52, '#000000', alpha=0.45)
        renderer.draw_text(16, 14, font, hud, '#FFFFFF')
        renderer.draw_text(16, 36, font, help_s, '#BBBBBB')
        renderer.flip()
        clock.tick(60)  # Cap at ~60 FPS.

    # Cleanup when we leave the loop.
    car.cleanup()
    renderer.unload_texture(map_tex)
    renderer.unload_texture(border_tex)
    renderer.cleanup()


if __name__ == '__main__':
    main()
