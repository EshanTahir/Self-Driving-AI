import os  # For file handling.
import pygame

current_dir = os.path.dirname(os.path.abspath(__file__))  # Create var containing the current directory, for all OS.
image_dir = os.path.join(current_dir, 'Images')  # Create var containing the images directory, for all OS.

map_1_real = pygame.image.load(os.path.join(image_dir, 'map_1_real.png'))
map_1_border = pygame.image.load(os.path.join(image_dir, 'map_1_border.png'))
map_1_checkpoints = [[2250, 1580], [2250, 2000], [2250, 2500], [2200, 2600], [2120, 2700], [1850, 2700], [1540, 2550], [1800, 2420], [2060,2280], [1800, 2150],
                     [1530, 2000], [1800,1870], [2070,1725], [1950,1600], [1400,1600], [1280,1950], [1280,2200],
                     [1280,2550], [1400,2890], [1700,2890], [2060,2890], [2500,2890], [2830,2800], [2830,2560],
                     [2830,2300], [2830,2070], [2830,1800], [2830,1560], [2830,1300], [2830,1050], [2830,800],
                     [2960,715], [3100,870], [3100,1870], [3100,2770], [3100, 2999], [3097,3100], [2710,3200], [2520,3143],
                     [2343,3200], [2130,3143], [1950,3200], [1750,3143], [1550,3200], [1350,3143], [1150,3200],
                     [880,3143], [650,3050], [640,2900], [640,1900], [640,850], [777,730], [1200,730], [1700,760],
                     [1860,800], [2170,800], [2260,930], [2130,1070], [1720,1070], [1300,1070], [1180,1120],
                     [1030,1210], [1180,1300], [1300, 1350], [1777, 1350], [2130, 1350]]

map_1_spawn_points = [[[2200, 1440], 0, 270], [[2918, 3115], 37, 180]]
map_1 = [map_1_real, map_1_border, map_1_spawn_points, map_1_checkpoints]

map_2_real = pygame.image.load(os.path.join(image_dir, 'map_2_real.png'))
map_2_border = pygame.image.load(os.path.join(image_dir, 'map_2_border.png'))
map_2_checkpoints = [[1202, 786], [1331, 786], [1459, 786], [1575, 810], [1597, 865], [1576, 912], [1459, 933],
                     [1331, 933], [1202, 933], [1075, 933], [947, 933], [819, 933], [702, 911], [682, 861], [700, 809],
                     [819, 770], [947, 770], [1075, 770]]

map_2_spawn_points = [[[1072, 759], 0, 360], [[1072, 907], 9, 180]]
map_2 = [map_2_real, map_2_border, map_2_spawn_points, map_2_checkpoints]

maps = [map_1, map_2]


def get_maps():
    return maps