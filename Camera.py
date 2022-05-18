import pygame

class Camera_Group(pygame.sprite.Group):
    def __init__(self, ground):
        super().__init__()
        self.screen = pygame.display.get_surface()

        self.offset = pygame.math.Vector2(0, 0)
        self.half_w = self.screen.get_size()[0]//2
        self.half_h = self.screen.get_size()[1]//2

        self.ground = ground
        self.ground_rect = ground.get_rect(topleft=(0,0))

    def center_target_camera(self, target):
        self.offset.x = target.rect.centerx - self.half_w
        self.offset.y = target.rect.centery - self.half_h

    def custom_draw(self, player, ground_enabled, sprites_enabled):
        self.center_target_camera(player)

        if ground_enabled:
            ground_offset = self.ground_rect.topleft-self.offset
            self.screen.blit(self.ground, ground_offset)
        if sprites_enabled:
            for sprite in sorted(self.sprites(), key=lambda sprite: sprite.rect.centery):
                offset_pos = sprite.rect.topleft - self.offset
                self.screen.blit(sprite.image, offset_pos)

    def individual_draw(self, player, ground_enabled, sprites_enabled):
        self.center_target_camera(player)

        if ground_enabled:
            ground_offset = self.ground_rect.topleft-self.offset
            self.screen.blit(self.ground, ground_offset)
        if sprites_enabled:
            self.screen.blit(player.image, player.rect.topleft-self.offset)

    def get_offset(self):
        return self.offset
