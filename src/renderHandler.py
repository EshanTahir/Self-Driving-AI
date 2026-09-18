# Import libraries.
import moderngl  # OpenGL bindings used for GPU drawing.
import numpy as np  # For matrix and color math.
import pygame  # The game engine / window creation.


# Class used to draw everything with OpenGL (maps, cars, textures for now).
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

        # Turn on blending for transparency.
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

        # Texture cache: maps an id to (texture, width, height).
        self.texture_cache = {}
        self.next_texture_id = 0

        # Build the basic textured-quad shader.
        self.create_shaders()

        # Build the fullscreen quad used for blitting textures.
        self.create_quad()

        # Offscreen framebuffer we draw into, then flip to the screen.
        self.render_texture = self.ctx.texture((width, height), 4)
        self.render_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.fbo = self.ctx.framebuffer(color_attachments=[self.render_texture])

        print('ModernGL Renderer initialized: ' + str(width) + 'x' + str(height))

    # Function to create shader programs (basic blit for now).
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

        # Simple blit / copy shader (no tint)  -  used when presenting the frame.
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

    # Function to create a unit quad for rendering.
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
        self.blit_vao = self.ctx.simple_vertex_array(
            self.blit_shader, self.quad_vbo, 'in_vert', 'in_texcoord'
        )

    # Function to create orthographic projection matrix - Pygame coordinate system (Y down).
    def get_projection_matrix(self):
        matrix = np.array([
            [2.0 / self.width, 0.0, 0.0, -1.0],
            [0.0, 2.0 / self.height, 0.0, -1.0],  # Positive Y starts at -1 (bottom), pygame-style.
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype='f4')

        return np.ascontiguousarray(matrix.T)

    # Function to create transformation matrix for positioning.
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

    # Function to free a texture from memory.
    def unload_texture(self, texture_id):
        if texture_id in self.texture_cache:
            texture, _, _ = self.texture_cache[texture_id]
            texture.release()
            del self.texture_cache[texture_id]

    # Function to clear the screen with a color.
    def clear(self, color=(0, 0, 0, 255)):
        r, g, b, a = color
        self.fbo.use()
        self.ctx.clear(r / 255.0, g / 255.0, b / 255.0, a / 255.0)

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

    # Function to display the rendered frame.
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

    # Function to get screen dimensions.
    def get_size(self):
        return (self.width, self.height)

    # Function to release all resources.
    def cleanup(self):
        # Free every texture we still have cached.
        for texture_id in list(self.texture_cache.keys()):
            self.unload_texture(texture_id)

        # Release the GL buffers / VAOs / framebuffer / context.
        self.quad_vbo.release()
        self.basic_vao.release()
        self.blit_vao.release()
        self.render_texture.release()
        self.fbo.release()
        self.ctx.release()
