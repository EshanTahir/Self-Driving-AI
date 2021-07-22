# Import libraries.
import neat  # The genetic algorithm handler.

from simHandler import run_car

# Run program.
if __name__ == "__main__":
    sim_length = 1000000
    config_path = "./config-feedforward.txt"  # Set the location for the configuration file.
    config = neat.config.Config(neat.DefaultGenome, neat.DefaultReproduction,
                                neat.DefaultSpeciesSet, neat.DefaultStagnation,
                                config_path)  # Setup NEAT configuration.

    # Create core evolution algorithm class
    p = neat.Population(config)

    # Add reporter for statistical results
    p.add_reporter(neat.StdOutReporter(True))
    stats = neat.StatisticsReporter()
    p.add_reporter(stats)

    # Run NEAT using run_car function, 'sim_length' amount of times.
    p.run(run_car, sim_length)
