# Import libraries.
import json  # For loading checkpoint / spawn data from disk.
import os  # For file handling.

import pygame  # The game engine.

from paths import DATA_DIR, IMAGES_DIR


# Function to load track checkpoint / spawn data from JSON, or fall back to hardcoded lists.
def load_track_data(map_name, fallback_checkpoints, fallback_spawns):
    # Prefer JSON written by checkpointMapper.py; fall back to the hardcoded lists.
    json_path = os.path.join(DATA_DIR, map_name + '_checkpoints.json')
    if os.path.isfile(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)  # Load the JSON file into a dict.
        checkpoints = [list(p) for p in data.get('checkpoints', fallback_checkpoints)]
        spawn_points = data.get('spawn_points', fallback_spawns)
        return checkpoints, spawn_points
    return fallback_checkpoints, fallback_spawns  # JSON missing  -  use the hardcoded fallbacks.


# Map 3  -  the active track used by the NEAT simulation.
map_3_real = pygame.image.load(os.path.join(IMAGES_DIR, 'map_3_real.png'))  # Visual track image.
map_3_border = pygame.image.load(os.path.join(IMAGES_DIR, 'map_3_border.png'))  # Collision / x-ray mask.

# Hardcoded fallbacks (used if the JSON file is missing).
map_3_checkpoints_fallback = [
    [1330, 1888], [1215, 1730], [1190, 1500], [1215, 1410], [1335, 1250],
    [1530, 1135], [1740, 1120], [1930, 1230], [1985, 1445], [2090, 1640],
    [2280, 1720], [2480, 1790], [2570, 1945], [2530, 2135], [2430, 2280],
    [2360, 2465],     [2330, 2640], [2222, 2790], [2080, 2880], [1900, 2900],
    [1860, 2910], [1710, 2910], [1560, 2810], [1440, 2690], [1390, 2530],
    [1375, 2360], [1370, 2170], [1385, 2025],
]
map_3_spawns_fallback = [
    [[1400, 2265], 0, 270],
    [[1436, 2356], 0, 270],
    [[1342, 2356], 0, 270],
    [[1302, 2265], 0, 270],
]

map_3_checkpoints, map_3_spawn_points = load_track_data(
    'map_3', map_3_checkpoints_fallback, map_3_spawns_fallback
)

# Pack map data: [real_image, border_image, spawn_points, checkpoints]
map_3 = [map_3_real, map_3_border, map_3_spawn_points, map_3_checkpoints]

maps = [map_3]  # Only maps listed here are used by the simulator.


# Function to grab the list of available maps.
def get_maps():
    return maps  # Returns the maps list to whatever calls this function.
