# Import libraries.
import os  # For file handling.

# Create var containing the project root (parent of src/), for all OS.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Create vars containing the resource folders (still flat Images / Miscellaneous for now).
IMAGES_DIR = os.path.join(ROOT_DIR, 'Images')  # Create var containing the images directory, for all OS.
MISC_DIR = os.path.join(ROOT_DIR, 'Miscellaneous')  # Create var containing the misc directory, for all OS.
FONTS_DIR = MISC_DIR  # Fonts still live under Miscellaneous for now.
