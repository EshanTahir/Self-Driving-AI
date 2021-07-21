import pygame
def draw(car, screen):
    surface = pygame.image.load('SupraCar.png')
    rotated_image = pygame.transform.rotate(surface, car.angle)
    new_rect = rotated_image.get_rect(center=surface.get_rect(topleft=car.position).center)
    new_rect.y += 6
    new_rect.x += 7
    screen.blit(rotated_image, new_rect)