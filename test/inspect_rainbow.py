import sys
import os
import zipfile

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.gui.emoji_renderer import get_assets_path

path, _ = get_assets_path()
print(f"Opening {path}")

with zipfile.ZipFile(path, 'r') as z:
    for name in z.namelist():
        if name.startswith("1f3f3"):
            print(name)