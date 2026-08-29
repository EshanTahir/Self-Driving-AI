# Import libraries.
import os  # For file handling.

# Create var containing the project root (parent of src/), for all OS.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Create vars containing the resource folders (res/ layout).
RES_DIR = os.path.join(ROOT_DIR, 'res')  # Create var containing the res directory, for all OS.
IMAGES_DIR = os.path.join(RES_DIR, 'images')  # Create var containing the images directory, for all OS.
FONTS_DIR = os.path.join(RES_DIR, 'fonts')  # Create var containing the fonts directory, for all OS.
