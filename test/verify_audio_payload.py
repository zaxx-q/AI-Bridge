import os
import base64
import json
from pathlib import Path

def verify_audio_payload(file_path):
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File {file_path} not found.")
        return

    # 1. Start with raw file size
    raw_size = path.stat().st_size
    raw_size_mb = raw_size / (1024 * 1024)
    print(f"File: {path.name}")
    print(f"Raw file size: {raw_size_mb:.2f} MB ({raw_size} bytes)")

    # 2. Read and base64 encode
    with open(path, "rb") as f:
        audio_bytes = f.read()
    
    base64_data = base64.b64encode(audio_bytes).decode("utf-8")
    base64_size = len(base64_data)
    base64_size_mb = base64_size / (1024 * 1024)
    print(f"Base64 encoded size: {base64_size_mb:.2f} MB ({base64_size} bytes)")
    print(f"Size increase: {((base64_size / raw_size) - 1) * 100:.2f}%")

    # 3. Construct payload as it would be sent to Gemini
    # This matches the 'inlineData' structure in Gemini API
    payload = {
        "contents": [{
            "parts": [
                {
                    "inlineData": {
                        "mimeType": "audio/mp4", # m4a is typically mp4
                        "data": base64_data
                    }
                },
                {"text": "Transcribe this audio."}
            ]
        }]
    }

    # 4. Measure total JSON payload size
    json_payload = json.dumps(payload)
    total_payload_size = len(json_payload)
    total_payload_mb = total_payload_size / (1024 * 1024)
    print(f"\nTotal JSON payload size: {total_payload_mb:.2f} MB ({total_payload_size} bytes)")

    if total_payload_mb > 20:
        print("\nWARNING: Payload exceeds 20 MB limit!")
        print("According to Gemini documentation, you MUST use the Files API for files > 20 MB.")
    else:
        print("\nPayload is within the 20 MB limit for inline data.")

if __name__ == "__main__":
    # Check if test/audio.m4a exists, otherwise use a placeholder or prompt
    audio_path = "test/audio.m4a"
    verify_audio_payload(audio_path)