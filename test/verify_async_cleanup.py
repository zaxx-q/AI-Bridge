import os
import sys
import tempfile
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gui.emoji_renderer import EmojiRenderer

def test_cleanup():
    print("Testing ASYNC cleanup logic...")
    
    # Create some fake stale directories
    temp_base = tempfile.gettempdir()
    stale_dirs = []
    for i in range(5):
        d = tempfile.mkdtemp(prefix="aipromptbridge_icons_")
        stale_dirs.append(d)
        
    print(f"Created {len(stale_dirs)} fake stale dirs")
    print(f"Verifying existence before init: {all(os.path.exists(d) for d in stale_dirs)}")
    
    # Initialize renderer - should trigger background thread
    print("\nInitializing EmojiRenderer (allocates new dir immediately)...")
    start_time = time.time()
    renderer = EmojiRenderer()
    init_time = time.time() - start_time
    print(f"Initialization took {init_time:.4f}s")
    
    # Check current temp dir is created
    current_temp = renderer._temp_icon_dir
    print(f"Current temp dir: {current_temp}")
    if not os.path.exists(current_temp):
        print("FAILURE: Current temp dir not created on init")
        return

    # Wait for background thread to finish
    print("Waiting for background cleanup...")
    time.sleep(1.0) # Should be plenty of time for 5 empty dirs
    
    # Check if stale dirs are gone
    remaining = [d for d in stale_dirs if os.path.exists(d)]
    
    if not remaining:
        print("SUCCESS: All stale directories cleaned up asynchronously")
    else:
        print(f"FAILURE: Stale directories remaining: {remaining}")
        
    # Verify we didn't delete our own dir
    if os.path.exists(current_temp):
        print("SUCCESS: Current temp dir was preserved")
    else:
        print("FAILURE: Current temp dir was DELETED by mistake!")

    # Cleanup at end
    renderer.cleanup()

if __name__ == "__main__":
    test_cleanup()