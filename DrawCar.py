import pygame
import os

def draw(car, screen, image_dir):
    surface = pygame.image.load(os.path.join(image_dir, 'SupraCar.png')).convert_alpha()
    rotated_image = pygame.transform.rotate(surface, car.angle)
    new_rect = rotated_image.get_rect(center=surface.get_rect(topleft=car.position).center)
    new_rect.y += 6
    new_rect.x += 7
    screen.blit(rotated_image, new_rect)