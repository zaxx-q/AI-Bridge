#!/usr/bin/env python3
import sys
import json
import configparser
from pathlib import Path

def compare():
    config_path = Path("config.ini.old")
    json_path = Path("prompts.json")

    if not config_path.exists():
        print(f"Error: {config_path} not found")
        return
    if not json_path.exists():
        print(f"Error: {json_path} not found")
        return

    # Load INI endpoints
    # Custom parser to handle the specific format if needed, but standard configparser with allow_no_value=True might work
    # However, since the user's INI file has some very long lines and specific formatting, let's parse it manually to be safe
    ini_endpoints = {}
    with open(config_path, 'r', encoding='utf-8') as f:
        in_endpoints = False
        for line in f:
            line = line.strip()
            if not line: continue
            
            if line.lower() == "[endpoints]":
                in_endpoints = True
                continue
            
            if in_endpoints and line.startswith("["):
                in_endpoints = False
                continue
            
            if in_endpoints and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                ini_endpoints[key.strip()] = val.strip()

    # Load JSON endpoints
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        json_endpoints = data.get("endpoints", {})
        # Remove _settings
        if "_settings" in json_endpoints:
            del json_endpoints["_settings"]

    # Compare
    all_keys = sorted(set(ini_endpoints.keys()) | set(json_endpoints.keys()))
    
    matches = 0
    mismatches = 0
    missing_in_json = 0
    missing_in_ini = 0

    print(f"{'Endpoint':<25} | {'Status'}")
    print("-" * 40)

    # Force UTF-8 output for Windows console
    if sys.platform == 'win32':
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

    for key in all_keys:
        ini_val = ini_endpoints.get(key)
        json_val = json_endpoints.get(key)

        if ini_val == json_val:
            sys.stdout.write(f"{key:<25} | OK Match\n")
            matches += 1
        elif ini_val is None:
            sys.stdout.write(f"{key:<25} | NEW Only in JSON\n")
            missing_in_ini += 1
        elif json_val is None:
            sys.stdout.write(f"{key:<25} | MISSING in JSON\n")
            missing_in_json += 1
        else:
            sys.stdout.write(f"{key:<25} | ERROR Mismatch!\n")
            mismatches += 1
            # print(f"  INI:  {ini_val[:50]}...")
            # print(f"  JSON: {json_val[:50]}...")

    print("-" * 40)
    print(f"Summary:")
    print(f"  Total Keys:      {len(all_keys)}")
    print(f"  Verbatim Matches: {matches}")
    print(f"  Mismatches:      {mismatches}")
    print(f"  Missing in JSON: {missing_in_json}")
    print(f"  New in JSON:     {missing_in_ini}")

if __name__ == "__main__":
    compare()