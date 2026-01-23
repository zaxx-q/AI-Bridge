#!/usr/bin/env python3
"""
Verify attachment persistence and session serialization.
"""

import os
import sys
import shutil
import base64
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session_manager import ChatSession
from src.attachment_manager import AttachmentManager

def create_test_image_b64():
    """Create a simple 1x1 white pixel png base64 string using PIL"""
    from PIL import Image
    import io
    
    # Create 1x1 white pixel image
    img = Image.new('RGB', (1, 1), color='white')
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('ascii')

def test_manual_attachment_flow():
    print("\n--- Testing Manual Attachment Flow ---")
    
    session_id = 999999
    
    # 1. Create fake image data
    img_b64 = create_test_image_b64()
    mime_type = "image/png"
    
    print(f"Created test image base64 (len={len(img_b64)})")
    
    # 2. Save via AttachmentManager
    print(f"Saving to session {session_id}...")
    path = AttachmentManager.save_image(
        session_id=session_id,
        image_base64=img_b64,
        mime_type=mime_type,
        message_index=0,
        original_filename="test_pixel.png"
    )
    
    print(f"Saved to: {path}")
    assert path is not None
    assert os.path.exists(path)
    
    # 3. Create Session manually with attachment
    print("Creating ChatSession with attachment...")
    session = ChatSession(session_id=session_id)
    session.attachments = [{"path": path, "mime_type": mime_type}]
    
    # 4. Serialize
    print("Serializing session...")
    data = session.to_dict()
    print(f"Serialized attachments: {json.dumps(data.get('attachments'), indent=2)}")
    
    assert len(data["attachments"]) == 1
    assert data["attachments"][0]["path"] == path
    
    # 5. Deserialize
    print("Deserializing to new session...")
    new_session = ChatSession.from_dict(data)
    
    # Check if backward compatibility filled image_base64
    print(f"New session image_base64 present: {bool(new_session.image_base64)}")
    assert new_session.image_base64 is not None
    assert len(new_session.image_base64) > 0
    
    # Check if we can load the image from the path explicitly
    print(f"Loading image from path: {new_session.attachments[0]['path']}")
    loaded_b64, loaded_mime = AttachmentManager.load_image(new_session.attachments[0]['path'])
    assert loaded_b64 is not None
    assert len(loaded_b64) > 0
    assert loaded_mime == "image/webp" # Default conversion is webp
    
    print("✅ Manual flow verified")
    
    # Cleanup
    AttachmentManager.delete_session_attachments(session_id)

def test_migration_flow():
    print("\n--- Testing Migration Flow ---")
    
    session_id = 888888
    img_b64 = create_test_image_b64()
    mime_type = "image/png"
    
    # 1. Create legacy session (memory only)
    print("Creating legacy session (in-memory image)...")
    session = ChatSession(session_id=session_id, image_base64=img_b64, mime_type=mime_type)
    assert session.attachments == []
    assert session.image_base64 == img_b64
    
    # 2. Serialize (should trigger migration)
    print("Serializing (should migrate)...")
    data = session.to_dict()
    
    print(f"Serialized attachments: {json.dumps(data.get('attachments'), indent=2)}")
    assert len(data["attachments"]) == 1
    path = data["attachments"][0]["path"]
    assert os.path.exists(path)
    
    # 3. Validate original session updated
    assert len(session.attachments) == 1
    # Note: image_base64 remains in memory for current session
    
    print("✅ Migration flow verified")
    
    # Cleanup
    AttachmentManager.delete_session_attachments(session_id)

if __name__ == "__main__":
    try:
        test_manual_attachment_flow()
        test_migration_flow()
        print("\n✨ All tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
