
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.providers.gemini_native import GeminiNativeProvider
from src.providers.openai_compatible import OpenAICompatibleProvider

def test_gemini_reordering():
    print("Testing Gemini Native Reordering...")
    provider = GeminiNativeProvider(config={})
    
    # Case 1: Single Image, Text -> Should become Image, Text
    content_Simple = [
        {"type": "text", "text": "Analyze this"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
    ]
    parts = provider._convert_content_to_parts(content_Simple)
    # Check order: non-text (media) should be first
    if "text" not in parts[0] and "text" in parts[1]:
        print("  ✅ Case 1 (Single Media): Correctly reordered to Media First")
    else:
        print(f"  ❌ Case 1 Failed: {parts}")
        
    # Case 2: Mixed Interleaved -> Should preserve order
    content_Mixed = [
        {"type": "text", "text": "Part 1"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,111"}},
        {"type": "text", "text": "Part 2"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,222"}}
    ]
    parts = provider._convert_content_to_parts(content_Mixed)
    
    # Expect: Text, Media, Text, Media
    # Note: Gemini parts structure might differ (inline_data vs text)
    is_text_0 = "text" in parts[0]
    is_media_1 = "inline_data" in parts[1]
    is_text_2 = "text" in parts[2]
    is_media_3 = "inline_data" in parts[3]
    
    if is_text_0 and is_media_1 and is_text_2 and is_media_3:
        print("  ✅ Case 2 (Multiple Media): Correctly preserved order")
    else:
        print(f"  ❌ Case 2 Failed: {[k for p in parts for k in p.keys()]}")

def test_openrouter_reordering():
    print("\nTesting OpenRouter Reordering...")
    # Mocking config/check
    provider = OpenAICompatibleProvider("openrouter", "https://openrouter.ai/api/v1", config={})
    
    # Case 1: Image, Text -> Should become Text, Image (Text First)
    content_Simple = [
        {"type": "image_url", "image_url": {"url": "..."}},
        {"type": "text", "text": "Analyze this"}
    ]
    
    parts = provider._reorder_content_for_provider(content_Simple)
    
    if parts[0]["type"] == "text" and parts[1]["type"] == "image_url":
        print("  ✅ Case 1 (Single Media): Correctly reordered to Text First")
    else:
        print(f"  ❌ Case 1 Failed: {[p.get('type') for p in parts]}")
        
    # Case 2: Mixed Interleaved -> Should preserve order
    content_Mixed = [
        {"type": "text", "text": "Part 1"},
        {"type": "image_url", "image_url": {"url": "..."}},
        {"type": "text", "text": "Part 2"},
        {"type": "image_url", "image_url": {"url": "..."}}
    ]
    
    parts = provider._reorder_content_for_provider(content_Mixed)
    
    types = [p.get("type") for p in parts]
    if types == ["text", "image_url", "text", "image_url"]:
        print("  ✅ Case 2 (Multiple Media): Correctly preserved order")
    else:
         print(f"  ❌ Case 2 Failed: {types}")

if __name__ == "__main__":
    try:
        test_gemini_reordering()
        test_openrouter_reordering()
    except Exception as e:
        print(f"Error during testing: {e}")
