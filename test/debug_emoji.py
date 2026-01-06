import sys
import os

# Add project root to path (one level up from test/)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

# Import via src package to allow relative imports to work
from src.gui.emoji_renderer import EmojiRenderer, get_assets_path
import emoji

def test_renderer():
    print(f"Emoji library version: {emoji.__version__}")
    
    renderer = EmojiRenderer()
    print(f"Assets path: {renderer.assets_path}")
    print(f"Is Zip: {renderer.is_zip}")
    
    # Test cases: [Description, String]
    test_cases = [
        ("Simple Smile", "😀"),
        ("Family (ZWJ)", "👨‍👩‍👧"),
        ("Thumbs Up Dark Skin", "👍🏿"),
        ("Rainbow Flag", "🏳️‍🌈"),
        
        # New Failures
        ("Shaking Face (15.0)", "🫨"),
        ("Goose (15.0)", "🪿"),
        ("Brown Mushroom (15.1)", "🍄‍🟫"),
        ("Family Gender Neutral (15.1)", "🧑‍🧑‍🧒"),
        ("Runner Right (15.1)", "🏃‍➡️"),
    ]

    print("\n--- Testing Emoji Parsing & Loading ---\n")
    
    for desc, text in test_cases:
        print(f"TestCase: {desc}")
        print(f"  Input: {ascii(text)}")
        
        # 1. Parse
        detected = renderer.find_emojis(text)
        print(f"  Detected ({len(detected)}):")
        
        for start, end, char in detected:
            filename = renderer.get_codepoint_filename(char)
            # Try to load
            img = renderer._load_pil_image(char)
            status = "FOUND" if img else "MISSING"
            
            print(f"    - Char: {ascii(char)}")
            print(f"      Filename expected: {filename}.png")
            print(f"      Status: {status}")
            
            if status == "MISSING":
                # Check for variations in the zip if possible
                if renderer.zip_file:
                    print(f"      Looking for partial matches in zip...")
                    # very naive search
                    for name in renderer.zip_file.namelist():
                        if filename in name:
                            print(f"        Found similar: {name}")

        print("")

if __name__ == "__main__":
    test_renderer()