# Import libraries.
import pygame  # The game engine.


# Class used to follow a car and compute a world-to-screen offset.
# Drawing itself is handled by the OpenGL renderer; this only tracks the view.
class Camera_Group:
    def __init__(self, screen_width, screen_height, smooth_factor=0.18, look_ahead=0.35):
        self.offset = pygame.math.Vector2(0, 0)  # Variable to see the current world scroll offset.
        self.target_offset = pygame.math.Vector2(0, 0)  # Variable to see the desired offset this frame.
        self.half_w = screen_width // 2  # Half screen width, used for centering.
        self.half_h = screen_height // 2  # Half screen height, used for centering.
        self.smooth_factor = smooth_factor  # How quickly the camera eases toward the target.
        self.look_ahead = look_ahead  # Bias the view slightly in the drive direction.
        self.initialized = False  # Snap once on the first target so we don't ease from (0,0).
        self.vel = pygame.math.Vector2(0, 0)  # Variable used to smooth how the camera moves.

    # Function to center the camera on a target car (with a little look-ahead).
    def center_target_camera(self, target, dt=1 / 60):
        # Aim slightly ahead of the car so turns feel less twitchy.
        import math
        ahead = target.speed * self.look_ahead
        look_x = target.position.x + math.cos(target.rotation) * ahead  # X point to look at.
        look_y = target.position.y + math.sin(target.rotation) * ahead  # Y point to look at.

        self.target_offset.x = look_x - self.half_w  # Desired scroll so the look point is centered.
        self.target_offset.y = look_y - self.half_h

        if not self.initialized:
            self.offset.update(self.target_offset)  # Snap instantly on first frame.
            self.vel.update(0, 0)
            self.initialized = True
            return

        # Ease the camera toward the target so it doesn't jitter as much as a raw lerp.
        dt = max(dt, 1e-4)
        stiffness = 18.0 * self.smooth_factor / 0.18  # How snappy the ease is.
        damping = 2.0 * (stiffness ** 0.5)  # How much we slow the ease down.

        err_x = self.target_offset.x - self.offset.x  # How far off we are on x.
        acc_x = stiffness * err_x - damping * self.vel.x  # How hard to push this frame.
        self.vel.x = self.vel.x + acc_x * dt  # Update camera velocity.
        self.offset.x = self.offset.x + self.vel.x * dt  # Update offset.

        err_y = self.target_offset.y - self.offset.y  # How far off we are on y.
        acc_y = stiffness * err_y - damping * self.vel.y  # How hard to push this frame.
        self.vel.y = self.vel.y + acc_y * dt  # Update camera velocity.
        self.offset.y = self.offset.y + self.vel.y * dt  # Update offset.

    # Function to grab the current camera offset for drawing.
    def get_offset(self):
        return self.offset  # Returns the current offset to whatever calls this function.

    # Function to free-cam nudge in world pixels (positive dx pans view rightward content left).
    def pan(self, dx, dy):
        self.offset.x += dx
        self.offset.y += dy
        self.target_offset.update(self.offset)  # Keep target in sync so we don't spring back.
        self.vel.update(0, 0)

    # Function to instantly center on a world point (used when toggling back to follow).
    def snap_to(self, world_x, world_y):
        self.offset.x = world_x - self.half_w
        self.offset.y = world_y - self.half_h
        self.target_offset.update(self.offset)
        self.vel.update(0, 0)
        self.initialized = True
