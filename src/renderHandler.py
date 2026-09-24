# Import libraries.
import math  # For line / rotation math.

import moderngl  # OpenGL bindings used for GPU drawing.
import numpy as np  # For matrix and color math.
import pygame  # The game engine / window creation.


# Class used to draw everything with OpenGL (maps, cars, lines, text, buttons).
class Renderer:
    # Function to set up the OpenGL window, shaders, and caches.
    def __init__(self, width, height, fullscreen=False, vsync=False):
        # Create a pygame OpenGL window and a ModernGL context to draw into.
        flags = pygame.OPENGL | pygame.DOUBLEBUF
        if fullscreen:
            flags |= pygame.FULLSCREEN

        vsync_flag = 1 if vsync else 0
        try:
            self.display = pygame.display.set_mode((width, height), flags, vsync=vsync_flag)
        except TypeError:
            self.display = pygame.display.set_mode((width, height), flags)
        self.ctx = moderngl.create_context()
        self.width = width
        self.height = height

        # Turn on blending for transparency, and point size so soft circles work.
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        try:
            self.ctx.enable(moderngl.PROGRAM_POINT_SIZE)
        except Exception:
            pass

        # Texture cache: maps an id to (texture, width, height).
        self.texture_cache = {}
        self.next_texture_id = 0

        # Cache for text textures so we don't rebuild the same string every frame.
        self.font_cache = {}

        # Build all the shader programs we need.
        self.create_shaders()

        # Build the fullscreen quad used for blitting textures.
        self.create_quad()

        # Build the simple geometry buffers for lines and circles.
        self.create_geometry()

        # Offscreen framebuffer we draw into, then flip to the screen.
        self.render_texture = self.ctx.texture((width, height), 4)
        self.render_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.fbo = self.ctx.framebuffer(color_attachments=[self.render_texture])

        print("ModernGL Renderer initialized: " + str(width) + "x" + str(height))

    # Function to create all shader programs.
    def create_shaders(self):
        # Basic textured quad shader (color tint + alpha).
        self.basic_shader = self.ctx.program(
            vertex_shader='''
                #version 330
                in vec2 in_vert;
                in vec2 in_texcoord;
                out vec2 v_text;

                uniform mat4 transform;
                uniform mat4 projection;

                void main() {
                    v_text = in_texcoord;
                    gl_Position = projection * transform * vec4(in_vert, 0.0, 1.0);
                }
            ''',
            fragment_shader='''
                #version 330
                uniform sampler2D texture0;
                uniform vec4 color_mod;
                uniform float alpha;

                in vec2 v_text;
                out vec4 f_color;

                void main() {
                    vec4 tex_color = texture(texture0, v_text);
                    f_color = tex_color * color_mod * vec4(1.0, 1.0, 1.0, alpha);
                }
            ''',
        )

        # Shader used when rotating a texture into a new texture.
        self.rotation_shader = self.ctx.program(
            vertex_shader='''
                #version 330
                in vec2 in_vert;
                in vec2 in_texcoord;
                out vec2 v_text;

                uniform mat4 transform;
                uniform mat4 projection;

                void main() {
                    v_text = in_texcoord;
                    gl_Position = projection * transform * vec4(in_vert, 0.0, 1.0);
                }
            ''',
            fragment_shader='''
                #version 330
                uniform sampler2D texture0;
                uniform float alpha;

                in vec2 v_text;
                out vec4 f_color;

                void main() {
                    vec4 tex_color = texture(texture0, v_text);
                    f_color = tex_color * vec4(1.0, 1.0, 1.0, alpha);
                }
            ''',
        )

        # Simple blit / copy shader (no tint).
        self.blit_shader = self.ctx.program(
            vertex_shader='''
                #version 330
                in vec2 in_vert;
                in vec2 in_texcoord;
                out vec2 v_text;

                void main() {
                    v_text = in_texcoord;
                    gl_Position = vec4(in_vert, 0.0, 1.0);
                }
            ''',
            fragment_shader='''
                #version 330
                uniform sampler2D texture0;
                in vec2 v_text;
                out vec4 f_color;

                void main() {
                    f_color = texture(texture0, v_text);
                }
            ''',
        )

        # Solid filled rectangle shader.
        self.rect_shader = self.ctx.program(
            vertex_shader='''
                #version 330
                in vec2 in_vert;
                uniform mat4 transform;
                uniform mat4 projection;

                void main() {
                    gl_Position = projection * transform * vec4(in_vert, 0.0, 1.0);
                }
            ''',
            fragment_shader='''
                #version 330
                uniform vec4 color;
                uniform float alpha;
                out vec4 f_color;

                void main() {
                    f_color = color * vec4(1.0, 1.0, 1.0, alpha);
                }
            ''',
        )

        # Line shader (same idea as the rect shader, drawn as lines).
        self.line_shader = self.ctx.program(
            vertex_shader='''
                #version 330
                in vec2 in_vert;
                uniform mat4 transform;
                uniform mat4 projection;

                void main() {
                    gl_Position = projection * transform * vec4(in_vert, 0.0, 1.0);
                }
            ''',
            fragment_shader='''
                #version 330
                uniform vec4 color;
                uniform float alpha;
                out vec4 f_color;

                void main() {
                    f_color = color * vec4(1.0, 1.0, 1.0, alpha);
                }
            ''',
        )

        # Circle shader - one point, fragment shader makes it round.
        self.circle_shader = self.ctx.program(
            vertex_shader='''
                #version 330
                in vec2 in_vert;
                in float in_radius;
                out float v_radius;

                uniform mat4 transform;
                uniform mat4 projection;

                void main() {
                    v_radius = in_radius;
                    gl_Position = projection * transform * vec4(in_vert, 0.0, 1.0);
                    gl_PointSize = in_radius * 2.0;
                }
            ''',
            fragment_shader='''
                #version 330
                in float v_radius;
                uniform vec4 color;
                uniform float alpha;
                out vec4 f_color;

                void main() {
                    vec2 coord = gl_PointCoord - vec2(0.5);
                    float dist = length(coord);

                    if (dist > 0.5) {
                        discard;
                    }

                    // Soften the circle edge a bit.
                    float edge = 1.0 - smoothstep(0.45, 0.5, dist);
                    f_color = color * vec4(1.0, 1.0, 1.0, alpha * edge);
                }
            ''',
        )

    # Function to create a unit quad for rendering
    def create_quad(self):
        vertices = np.array([
            # x, y,      u, v
            -1.0, -1.0, 0.0, 1.0,
            1.0, -1.0, 1.0, 1.0,
            -1.0, 1.0, 0.0, 0.0,
            1.0, 1.0, 1.0, 0.0,
        ], dtype='f4')

        vertices = np.ascontiguousarray(vertices)

        self.quad_vbo = self.ctx.buffer(vertices)

        # Make a VAO for each shader that uses the quad.
        self.basic_vao = self.ctx.simple_vertex_array(
            self.basic_shader, self.quad_vbo, 'in_vert', 'in_texcoord'
        )
        self.rotation_vao = self.ctx.simple_vertex_array(
            self.rotation_shader, self.quad_vbo, 'in_vert', 'in_texcoord'
        )
        self.blit_vao = self.ctx.simple_vertex_array(
            self.blit_shader, self.quad_vbo, 'in_vert', 'in_texcoord'
        )

        # Rectangle vertices (no texture coords needed for solid rects).
        rect_vertices = np.array([
            -1.0, -1.0,
            1.0, -1.0,
            -1.0, 1.0,
            1.0, 1.0,
        ], dtype='f4')

        rect_vertices = np.ascontiguousarray(rect_vertices)
        self.rect_vbo = self.ctx.buffer(rect_vertices)
        self.rect_vao = self.ctx.simple_vertex_array(
            self.rect_shader, self.rect_vbo, 'in_vert'
        )

    # Function to create geometry buffers for lines and circles
    def create_geometry(self):
        # Unit line along X: (-1, 0) -> (1, 0).
        # Transform scales length on X and thickness on Y, then rotates
        # so a diagonal line is just this unit line stretched and spun.
        line_vertices = np.array([
            -1.0, 0.0,
            1.0, 0.0,
        ], dtype='f4')

        line_vertices = np.ascontiguousarray(line_vertices)
        self.line_vbo = self.ctx.buffer(line_vertices)
        self.line_vao = self.ctx.simple_vertex_array(
            self.line_shader, self.line_vbo, 'in_vert'
        )

        # Circle geometry is just one point; the shader turns it into a soft circle.
        circle_vertices = np.array([
            0.0, 0.0, 1.0,  # x, y, radius
        ], dtype='f4')

        circle_vertices = np.ascontiguousarray(circle_vertices)
        self.circle_vbo = self.ctx.buffer(circle_vertices)
        self.circle_vao = self.ctx.simple_vertex_array(
            self.circle_shader, self.circle_vbo, 'in_vert', 'in_radius'
        )

    # Function to create orthographic projection matrix - Pygame coordinate system (Y down)
    def get_projection_matrix(self):
        matrix = np.array([
            [2.0 / self.width, 0.0, 0.0, -1.0],
            [0.0, 2.0 / self.height, 0.0, -1.0],  # Positive Y starts at -1 (bottom), pygame-style.
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype='f4')

        return np.ascontiguousarray(matrix.T)

    # Function to create transformation matrix for positioning and rotation
    def create_transform_matrix(self, x, y, width, height, angle=0.0):
        # Center point of the quad in screen space.
        tx = x + width / 2.0
        ty = y + height / 2.0

        # Rotation amount in radians.
        cos_a = np.cos(angle)
        sin_a = np.sin(angle)

        # Half-size scale (unit quad goes from -1..1).
        sx = width / 2.0
        sy = height / 2.0

        # Combined transform: scale, rotate, then put it at (tx, ty).
        transform = np.array([
            [sx * cos_a, -sx * sin_a, 0.0, tx],
            [sy * sin_a, sy * cos_a, 0.0, ty],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype='f4').T

        return np.ascontiguousarray(transform)

    # Function to make a transform matrix for a line segment.
    # Unit geometry is a horizontal line (-1,0)->(1,0).
    # We scale (length, thickness), then rotate.
    def create_line_transform_matrix(self, x1, y1, x2, y2, width=1.0):
        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1e-6:
            length = 1e-6
        angle = math.atan2(dy, dx)

        # Move the line so its middle sits at the midpoint of the two ends.
        tx = (x1 + x2) / 2.0
        ty = (y1 + y2) / 2.0

        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        # Scale length on X and thickness on Y, then rotate into place.
        sx = length / 2.0
        sy = max(width, 1.0) / 2.0

        transform = np.array([
            [sx * cos_a, -sy * sin_a, 0.0, tx],
            [sx * sin_a, sy * cos_a, 0.0, ty],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype='f4').T

        return np.ascontiguousarray(transform)

    # Function to convert a pygame surface to a ModernGL texture.
    # Returns a texture ID that can be used for rendering.
    def load_surface(self, pygame_surface):
        # Make sure the surface has an alpha channel.
        if pygame_surface.get_flags() & pygame.SRCALPHA:
            surface = pygame_surface
        else:
            surface = pygame_surface.convert_alpha()

        # Grab the pixel bytes; flip vertically because OpenGL's Y is upside-down vs pygame.
        width = surface.get_width()
        height = surface.get_height()
        image_data = pygame.image.tobytes(surface, 'RGBA', True)  # True flips vertically for OpenGL.

        # Upload the pixels as a ModernGL texture.
        texture = self.ctx.texture((width, height), 4, image_data)
        texture.filter = (moderngl.LINEAR, moderngl.LINEAR)

        # Remember it in the cache under a new id.
        texture_id = self.next_texture_id
        self.next_texture_id += 1
        self.texture_cache[texture_id] = (texture, width, height)

        return texture_id

    # Function to create a texture from text
    def create_text_texture(self, font, text, color=(0, 0, 0, 255)):
        # If color came in as a hex string, turn it into an RGBA tuple.
        if isinstance(color, str):
            color = self.hex_to_rgba(color)

        # Render the text onto a pygame surface first.
        text_surface = font.render(text, True, color[:3])

        # If the color has alpha < 255, multiply that onto the text surface.
        if len(color) == 4 and color[3] < 255:
            alpha_surface = pygame.Surface(text_surface.get_size(), pygame.SRCALPHA)
            alpha_surface.fill((255, 255, 255, color[3]))
            text_surface.blit(alpha_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        return self.load_surface(text_surface)

    # Function to free a texture from memory
    def unload_texture(self, texture_id):
        if texture_id in self.texture_cache:
            texture, _, _ = self.texture_cache[texture_id]
            texture.release()
            del self.texture_cache[texture_id]

    # Function to clear the screen with a color
    def clear(self, color=(0, 0, 0, 255)):
        r, g, b, a = color
        self.fbo.use()
        self.ctx.clear(r / 255.0, g / 255.0, b / 255.0, a / 255.0)

    # ----- Drawing functions -----

    # Function to draw a rectangle with optional transparency and rounded corners
    def draw_rectangle(self, x, y, width, height, color="#FFFFFF", alpha=1.0, border_radius=0):
        # Turn hex / tuple color into r,g,b,a ints.
        if isinstance(color, str) and color.startswith("#"):
            color = color.lstrip("#")
            if len(color) == 6:
                r = int(color[0:2], 16)
                g = int(color[2:4], 16)
                b = int(color[4:6], 16)
                a = 255
            else:
                r = int(color[0:2], 16)
                g = int(color[2:4], 16)
                b = int(color[4:6], 16)
                a = int(color[6:8], 16) if len(color) == 8 else 255
        elif isinstance(color, tuple):
            if len(color) == 3:
                r, g, b = color
                a = 255
            else:
                r, g, b, a = color
        else:
            r, g, b, a = 255, 255, 255, 255

        # If we need rounded corners or per-pixel alpha, draw with pygame then upload.
        if border_radius > 0 or (isinstance(color, tuple) and len(color) == 4):
            # Make a small pygame surface and draw the rect onto it.
            rect_surface = pygame.Surface((int(width), int(height)), pygame.SRCALPHA)
            rect_surface.fill((0, 0, 0, 0))  # Start fully transparent.

            # Draw with rounded corners if border_radius was set.
            if border_radius > 0:
                pygame.draw.rect(rect_surface, (r, g, b, a),
                                 rect_surface.get_rect(),
                                 border_radius=border_radius)
            else:
                pygame.draw.rect(rect_surface, (r, g, b, a), rect_surface.get_rect())

            # Upload that surface and blit it, then free the temp texture.
            texture_id = self.load_surface(rect_surface)
            self.blit(texture_id, x, y, alpha=alpha)
            self.unload_texture(texture_id)
        else:
            # Plain rectangle - just use the shader (faster than a pygame surface).
            projection = self.get_projection_matrix()
            transform = self.create_transform_matrix(x, y, width, height)

            self.rect_shader['projection'].write(projection)
            self.rect_shader['transform'].write(transform)
            self.rect_shader['color'].value = (r / 255.0, g / 255.0, b / 255.0, a / 255.0)
            self.rect_shader['alpha'].value = alpha

            # Draw the rectangle.
            self.fbo.use()
            self.rect_vao.render(moderngl.TRIANGLE_STRIP)

    # Function to draw text on screen
    def draw_text(self, x, y, font, text, color="#000000", alpha=1.0):
        # Reuse a cached text texture if we already made this string/color.
        color_tuple = self.hex_to_rgba(color) if isinstance(color, str) else color
        text_key = str(font.get_height()) + "_" + str(text) + "_" + str(color_tuple)

        if text_key in self.font_cache:
            texture_id = self.font_cache[text_key]
        else:
            # Cap the font cache so changing HUD numbers doesn't fill up GPU memory forever.
            if len(self.font_cache) > 120:
                old_key = next(iter(self.font_cache))
                old_id = self.font_cache.pop(old_key)
                self.unload_texture(old_id)
            texture_id = self.create_text_texture(font, text, color_tuple)
            self.font_cache[text_key] = texture_id

        # Draw the text texture.
        self.blit(texture_id, x, y, alpha=alpha)

    # Function to draw a line between two points
    def draw_line(self, x1, y1, x2, y2, color="#FFFFFF", width=1.0, alpha=1.0):
        # Turn hex / tuple color into r,g,b,a ints.
        if isinstance(color, str):
            r, g, b, a = self.hex_to_rgba(color)
        elif isinstance(color, tuple):
            if len(color) == 3:
                r, g, b = color
                a = 255
            else:
                r, g, b, a = color
        else:
            r, g, b, a = 255, 255, 255, 255

        # Build projection + transform for this line segment.
        projection = self.get_projection_matrix()
        transform = self.create_line_transform_matrix(x1, y1, x2, y2, width)

        # Feed the shader its projection / transform / color / alpha.
        self.line_shader['projection'].write(projection)
        self.line_shader['transform'].write(transform)
        self.line_shader['color'].value = (r / 255.0, g / 255.0, b / 255.0, a / 255.0)
        self.line_shader['alpha'].value = alpha

        # Draw the line (GL line width for thickness; transform handles the endpoints).
        self.fbo.use()
        try:
            self.ctx.line_width = max(float(width), 1.0)
        except Exception:
            pass
        self.line_vao.render(moderngl.LINES)

    # Function to draw a circle
    def draw_circle(self, x, y, radius, color="#FFFFFF", alpha=1.0):
        # Turn hex / tuple color into r,g,b,a ints.
        if isinstance(color, str):
            r, g, b, a = self.hex_to_rgba(color)
        elif isinstance(color, tuple):
            if len(color) == 3:
                r, g, b = color
                a = 255
            else:
                r, g, b, a = color
        else:
            r, g, b, a = 255, 255, 255, 255

        # Build projection + transform so the circle sits at (x, y).
        projection = self.get_projection_matrix()
        transform = self.create_transform_matrix(x - radius, y - radius, radius * 2, radius * 2)

        # Write the radius into the circle vertex buffer.
        circle_data = np.array([radius], dtype='f4')
        self.circle_vbo.write(circle_data.tobytes(), offset=8)  # Radius sits at float index 2.

        # Feed the shader its projection / transform / color / alpha.
        self.circle_shader['projection'].write(projection)
        self.circle_shader['transform'].write(transform)
        self.circle_shader['color'].value = (r / 255.0, g / 255.0, b / 255.0, a / 255.0)
        self.circle_shader['alpha'].value = alpha

        # Draw the circle as a GL point sprite.
        self.fbo.use()
        self.ctx.point_size = radius * 2
        self.circle_vao.render(moderngl.POINTS)

    # Function to draw a texture at the specified position.
    def blit(self, texture_id, x, y, width=None, height=None, alpha=1.0, source_rect=None):
        if texture_id not in self.texture_cache:
            return

        texture, tex_width, tex_height = self.texture_cache[texture_id]

        if width is None:
            width = tex_width
        if height is None:
            height = tex_height

        # Bind this texture to texture unit 0.
        texture.use(location=0)

        # Set projection / transform / sampler / alpha for the blit.
        projection = self.get_projection_matrix()
        transform = self.create_transform_matrix(x, y, width, height)

        self.basic_shader['projection'].write(projection)
        self.basic_shader['transform'].write(transform)
        self.basic_shader['texture0'].value = 0
        self.basic_shader['alpha'].value = alpha
        self.basic_shader['color_mod'].value = (1.0, 1.0, 1.0, 1.0)

        # Draw the textured quad into the offscreen framebuffer.
        self.fbo.use()
        self.basic_vao.render(moderngl.TRIANGLE_STRIP)

    # ----- Button system -----

    # Class used to make clickable UI buttons on top of the renderer.
    class Button:
        # Function to set up a button (colors, text, images, sounds, etc.).
        def __init__(self, renderer, font, x=0, y=0, width=150, height=100,
                     outline_width=6, image_outline=False, aa=False,
                     button_type="procedural", selected_box_color="#196985",
                     selected_text_color="#b2b2b2", hover_box_color="#2596be",
                     hover_text_color="#ffffff", box_color="#ffffff",
                     text_color="#2596be", outline_color="#000000",
                     text="button", selected_button_image=None,
                     hover_button_image=None, button_image=None,
                     hover_sound=None, click_sound=None, active=True,
                     click_type="left"):

            self.renderer = renderer
            self.clicked_down = False
            self.clicked_up = False
            self.hover = False

            self.button_type = button_type
            self.click_type = click_type

            # Keep colors as strings so text/texture caching keys stay simple.
            self.selected_box_color = selected_box_color
            self.selected_text_color = selected_text_color
            self.hover_box_color = hover_box_color
            self.hover_text_color = hover_text_color
            self.box_color = box_color
            self.text_color = text_color
            self.outline_width = outline_width
            self.outline_color = outline_color
            self.image_outline = image_outline

            self.text = text
            self.font = font
            self.aa = aa

            self.x = x
            self.y = y
            self.width = width
            self.height = height

            self.active = active

            self.hover_sound = hover_sound
            self.click_sound = click_sound

            self.hover_sound_played = False

            # Cache for this button's text textures (normal / hover / selected).
            self.text_cache = {}

            if self.button_type == "procedural" and button_image is None:
                # Procedural button - outline rect + box rect, text drawn with the renderer.
                self.outline_rect = (x - outline_width / 2, y - outline_width / 2,
                                     width + outline_width, height + outline_width)
                self.button_rect = (x, y, width, height)

                # Pre-make text textures for normal / hover / selected.
                self.create_text_textures()

            elif self.button_type == "image" and button_image is not None:
                # Image-based button - load the button images as textures.
                self.button_image_id = renderer.load_surface(button_image)
                self.selected_button_image_id = renderer.load_surface(
                    selected_button_image) if selected_button_image else None
                self.hover_button_image_id = renderer.load_surface(hover_button_image) if hover_button_image else None

                self.button_rect = (x, y, button_image.get_width(), button_image.get_height())

            else:
                raise ValueError('Button_type is not procedural or image')

        # Function to create text textures for all button states
        def create_text_textures(self):
            # Normal (idle) text
            normal_key = "normal_" + str(self.text) + "_" + str(self.text_color)
            if normal_key not in self.text_cache:
                self.text_cache[normal_key] = self.renderer.create_text_texture(
                    self.font, self.text, self.renderer.hex_to_rgba(self.text_color))

            # Hover text
            hover_key = "hover_" + str(self.text) + "_" + str(self.hover_text_color)
            if hover_key not in self.text_cache:
                self.text_cache[hover_key] = self.renderer.create_text_texture(
                    self.font, self.text, self.renderer.hex_to_rgba(self.hover_text_color))

            # Selected / clicked text
            selected_key = "selected_" + str(self.text) + "_" + str(self.selected_text_color)
            if selected_key not in self.text_cache:
                self.text_cache[selected_key] = self.renderer.create_text_texture(
                    self.font, self.text, self.renderer.hex_to_rgba(self.selected_text_color))

        # Function to display the button using the renderer
        def display_button(self):
            if self.button_type == "procedural":
                # Draw the outline behind the box.
                self.renderer.draw_rectangle(
                    self.outline_rect[0], self.outline_rect[1],
                    self.outline_rect[2], self.outline_rect[3],
                    self.outline_color
                )

                # Pick box color + which text texture based on click / hover state.
                if self.clicked_down:
                    box_color = self.selected_box_color
                    text_key = "selected_" + str(self.text) + "_" + str(self.selected_text_color)
                elif self.hover:
                    box_color = self.hover_box_color
                    text_key = "hover_" + str(self.text) + "_" + str(self.hover_text_color)
                else:
                    box_color = self.box_color
                    text_key = "normal_" + str(self.text) + "_" + str(self.text_color)

                # Draw the button box on top of the outline.
                self.renderer.draw_rectangle(
                    self.button_rect[0], self.button_rect[1],
                    self.button_rect[2], self.button_rect[3],
                    box_color
                )

                # Draw the text centered in the box.
                if text_key in self.text_cache:
                    text_texture_id = self.text_cache[text_key]
                    # Center the text inside the button box.
                    text_width = self.renderer.texture_cache[text_texture_id][1]
                    text_height = self.renderer.texture_cache[text_texture_id][2]
                    text_x = self.x + (self.width - text_width) // 2
                    text_y = self.y + (self.height - text_height) // 2
                    self.renderer.blit(text_texture_id, text_x, text_y)

            elif self.button_type == "image":
                # Pick which button image to show based on click / hover state.
                if self.clicked_down and self.selected_button_image_id is not None:
                    image_id = self.selected_button_image_id
                elif self.hover and self.hover_button_image_id is not None:
                    image_id = self.hover_button_image_id
                else:
                    image_id = self.button_image_id

                # Draw the button image.
                self.renderer.blit(image_id, self.x, self.y)

        # Function to check for button clicks
        def click_check(self, cursor_rect, events):
            # Check if the cursor is over this button.
            cursor_x, cursor_y = cursor_rect.topleft
            button_rect = pygame.Rect(self.button_rect)

            if button_rect.collidepoint(cursor_x, cursor_y):
                if self.click_type == "left":
                    if not self.clicked_down and "left_mouse_button_down" in events:
                        self.clicked_down = True
                        self.hover = False
                    elif not self.clicked_up and "left_mouse_button_up" in events:
                        if self.click_sound is not None:
                            pygame.mixer.Sound.play(self.click_sound)
                        self.clicked_down = False
                        self.clicked_up = True
                        self.hover = False
                    elif "left_mouse_button_down" not in events and "left_mouse_button_up" not in events:
                        if self.hover_sound is not None:
                            if not self.hover_sound_played:
                                pygame.mixer.Sound.play(self.hover_sound)
                                self.hover_sound_played = True
                        self.clicked_up = False
                        self.hover = True
                elif self.click_type == "right":
                    if not self.clicked_down and "right_mouse_button_down" in events:
                        self.clicked_down = True
                        self.hover = False
                    elif not self.clicked_up and "right_mouse_button_up" in events:
                        if self.click_sound is not None:
                            pygame.mixer.Sound.play(self.click_sound)
                        self.clicked_down = False
                        self.clicked_up = True
                        self.hover = False
                        return True
                    elif "right_mouse_button_down" not in events and "right_mouse_button_up" not in events:
                        if self.hover_sound is not None:
                            if not self.hover_sound_played:
                                pygame.mixer.Sound.play(self.hover_sound)
                                self.hover_sound_played = True
                        self.clicked_up = False
                        self.hover = True
                elif self.click_type == "scroll":
                    if not self.clicked_down and "scroll_mouse_button_down" in events:
                        self.clicked_down = True
                        self.hover = False
                    elif not self.clicked_up and "scroll_mouse_button_up" in events:
                        if self.click_sound is not None:
                            pygame.mixer.Sound.play(self.click_sound)
                        self.clicked_down = False
                        self.clicked_up = True
                        self.hover = False
                        return True
            else:
                self.clicked_down = False
                self.clicked_up = False
                self.hover = False
                self.hover_sound_played = False

            return False

        # Function to update and display the button
        def update(self, cursor_rect, events):
            if self.active:
                clicked = self.click_check(cursor_rect, events)
                self.display_button()
                return clicked
            return False

        # Function to clean up button resources
        def cleanup(self):
            if hasattr(self, 'text_cache'):
                for texture_id in self.text_cache.values():
                    self.renderer.unload_texture(texture_id)

            if hasattr(self, 'button_image_id'):
                self.renderer.unload_texture(self.button_image_id)
            if hasattr(self, 'selected_button_image_id') and self.selected_button_image_id:
                self.renderer.unload_texture(self.selected_button_image_id)
            if hasattr(self, 'hover_button_image_id') and self.hover_button_image_id:
                self.renderer.unload_texture(self.hover_button_image_id)

    # ----- Remaining renderer methods -----

    # Function to rotate a texture and return a new texture ID.
    # Meant to match pygame.transform.rotate() behavior.
    def rotate(self, texture_id, angle_degrees):
        if texture_id not in self.texture_cache:
            return texture_id

        texture, width, height = self.texture_cache[texture_id]

        # Turn degrees into radians.
        angle_rad = np.radians(angle_degrees)

        # New bounding box size after rotation (same math pygame uses).
        cos_a = abs(np.cos(angle_rad))
        sin_a = abs(np.sin(angle_rad))
        new_width = int(width * cos_a + height * sin_a)
        new_height = int(width * sin_a + height * cos_a)

        # Make a new texture big enough for the rotated image.
        rotated_texture = self.ctx.texture((new_width, new_height), 4)
        rotated_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        rotated_fbo = self.ctx.framebuffer(color_attachments=[rotated_texture])

        # Clear the new texture to fully transparent.
        rotated_fbo.use()
        self.ctx.clear(0.0, 0.0, 0.0, 0.0)

        # Bind the original texture so the shader can sample it.
        texture.use(location=0)

        # Use a normal orthographic projection here (no Y flip).
        projection = np.array([
            [2.0 / new_width, 0.0, 0.0, -1.0],
            [0.0, -2.0 / new_height, 0.0, 1.0],  # Standard top-down Y for the rotate pass.
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype='f4')
        projection = np.ascontiguousarray(projection.T)

        # Build the transform that centers + rotates the original quad.
        center_x = new_width / 2
        center_y = new_height / 2

        # Use angle_degrees as-is; pygame rotates counter-clockwise.
        angle_rad_gl = np.radians(angle_degrees)  # No need to negate the angle.

        # Half-size scale (unit quad goes from -1..1).
        sx = width / 2.0
        sy = height / 2.0

        # Build transform: scale, rotate, put at center of the new texture.
        cos_a_gl = np.cos(angle_rad_gl)
        sin_a_gl = np.sin(angle_rad_gl)

        transform = np.array([
            [sx * cos_a_gl, -sx * sin_a_gl, 0.0, center_x],
            [sy * sin_a_gl, sy * cos_a_gl, 0.0, center_y],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype='f4')
        transform = np.ascontiguousarray(transform.T)

        # Feed the shader its projection / transform / color / alpha.
        self.rotation_shader['projection'].write(projection)
        self.rotation_shader['transform'].write(transform)
        self.rotation_shader['texture0'].value = 0
        self.rotation_shader['alpha'].value = 1.0

        # Draw the rotated quad into the new texture.
        self.rotation_vao.render(moderngl.TRIANGLE_STRIP)

        # Stick the new texture in the cache and give it an id.
        new_texture_id = self.next_texture_id
        self.next_texture_id += 1
        self.texture_cache[new_texture_id] = (rotated_texture, new_width, new_height)

        # Switch back to the main offscreen framebuffer. to the main offscreen framebuffer.
        self.fbo.use()

        return new_texture_id

    # Function to scale a texture and return a new texture ID.
    def scale(self, texture_id, new_width, new_height):
        if texture_id not in self.texture_cache:
            return texture_id

        texture, width, height = self.texture_cache[texture_id]

        # Make a new texture at the requested size.
        scaled_texture = self.ctx.texture((new_width, new_height), 4)
        scaled_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        scaled_fbo = self.ctx.framebuffer(color_attachments=[scaled_texture])

        # Draw the old texture stretched into the new one.
        scaled_fbo.use()
        self.ctx.clear(0.0, 0.0, 0.0, 0.0)

        texture.use(location=0)
        self.blit_shader['texture0'].value = 0
        self.blit_vao.render(moderngl.TRIANGLE_STRIP)

        # Stick the new texture in the cache and give it an id.
        new_texture_id = self.next_texture_id
        self.next_texture_id += 1
        self.texture_cache[new_texture_id] = (scaled_texture, new_width, new_height)

        # Switch back to the main offscreen framebuffer.
        self.fbo.use()

        return new_texture_id

    # Function to display the rendered frame
    def flip(self):
        # Copy the offscreen framebuffer onto the real screen.
        self.ctx.screen.use()
        self.ctx.clear(0.0, 0.0, 0.0, 1.0)

        self.render_texture.use(location=0)
        self.blit_shader['texture0'].value = 0
        self.blit_vao.render(moderngl.TRIANGLE_STRIP)

        pygame.display.flip()

        # Clear the offscreen buffer so the next frame starts clean.
        self.fbo.use()
        self.ctx.clear(0.0, 0.0, 0.0, 0.0)

    # Function to get screen dimensions
    def get_size(self):
        return (self.width, self.height)

    # Function to draw a rectangle (filled or outline).
    def draw_rect(self, color, rect, width=0):
        x, y, w, h = rect
        r, g, b, a = color

        if width == 0:
            # Filled rectangle - just call draw_rectangle.
            self.draw_rectangle(x, y, w, h, color, a / 255.0)
        else:
            # Outline rectangle - draw four thin filled rects as the border.
            # Top edge
            self.draw_rectangle(x, y, w, width, color, a / 255.0)
            # Bottom edge
            self.draw_rectangle(x, y + h - width, w, width, color, a / 255.0)
            # Left edge
            self.draw_rectangle(x, y + width, width, h - 2 * width, color, a / 255.0)
            # Right edge
            self.draw_rectangle(x + w - width, y + width, width, h - 2 * width, color, a / 255.0)

    # Function to convert hex color to RGBA tuple
    def hex_to_rgba(self, hex_color):
        if isinstance(hex_color, tuple):
            return hex_color

        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 6:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return (r, g, b, 255)
        elif len(hex_color) == 8:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            a = int(hex_color[6:8], 16)
            return (r, g, b, a)
        return (0, 0, 0, 255)

    # Function to release all resources
    def cleanup(self):
        # Free everything in the font / text cache.
        for texture_id in list(self.font_cache.values()):
            if texture_id in self.texture_cache:
                texture, _, _ = self.texture_cache[texture_id]
                texture.release()
                del self.texture_cache[texture_id]

        # Free every texture we still have cached.
        for texture_id in list(self.texture_cache.keys()):
            self.unload_texture(texture_id)

        # Release the GL buffers / VAOs / framebuffer / context.
        self.quad_vbo.release()
        self.rect_vbo.release()
        self.line_vbo.release()
        self.circle_vbo.release()
        self.basic_vao.release()
        self.rotation_vao.release()
        self.blit_vao.release()
        self.rect_vao.release()
        self.line_vao.release()
        self.circle_vao.release()
        self.render_texture.release()
        self.fbo.release()
        self.ctx.release()


# Helper functions so older call sites still work.
# Function to create a button (thin wrapper around Renderer.Button).
def create_button(renderer, font, **kwargs):
    return renderer.Button(renderer, font, **kwargs)


# Function to draw a rectangle (thin wrapper).
def draw_rectangle(renderer, x, y, width, height, color="#FFFFFF", alpha=1.0):
    renderer.draw_rectangle(x, y, width, height, color, alpha)


# Function to draw text (thin wrapper).
def draw_text(renderer, x, y, font, text, color="#000000", alpha=1.0):
    renderer.draw_text(x, y, font, text, color, alpha)


# Function to draw a line (thin wrapper).
def draw_line(renderer, x1, y1, x2, y2, color="#FFFFFF", width=1.0, alpha=1.0):
    renderer.draw_line(x1, y1, x2, y2, color, width, alpha)


# Function to draw a circle (thin wrapper).
def draw_circle(renderer, x, y, radius, color="#FFFFFF", alpha=1.0):
    renderer.draw_circle(x, y, radius, color, alpha)
