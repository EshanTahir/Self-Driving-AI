# ToDo: Features to add:
# ToDo: Implement in-house genetic algorithm
# ToDo: Add weather changes, obstacles, and environment changes to simulation.

# ToDo: Create program to make checkpoints
# ToDo: Add feature to indicate when best car changes
# ToDo: Add play pause button

# Todo: Refactor code.

# 8 pixels == 5 irl inches. 101376 pixels == 1 mile.


# Import libraries.
import os  # For file handling.
import sys  # To be used for putting src/ on the import path.

# Put src/ on the import path so modules resolve like a normal package layout.
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))  # Create var containing the project root, for all OS.
sys.path.insert(0, os.path.join(ROOT_DIR, 'src'))

import neat  # The genetic algorithm handler.

from SimHandler import run_car

# Run program.
if __name__ == '__main__':
    sim_length = 1000000
    config_path = os.path.join(ROOT_DIR, 'config-feedforward.txt')  # Set the location for the configuration file.
    config = neat.config.Config(
        neat.DefaultGenome,
        neat.DefaultReproduction,
        neat.DefaultSpeciesSet,
        neat.DefaultStagnation,
        config_path,
    )  # Setup NEAT configuration.

    # Create core evolution algorithm class
    p = neat.Population(config)

    # Add reporter for statistical results
    p.add_reporter(neat.StdOutReporter(True))
    stats = neat.StatisticsReporter()
    p.add_reporter(stats)

    # Run NEAT using run_car function, 'sim_length' amount of times.
    p.run(run_car, sim_length)
