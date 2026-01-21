#!/usr/bin/env python3
"""
Verify Sync between tools_config.json and src/tools/defaults.py
"""
import sys
import json
import os
from pathlib import Path

# Add src to path to import defaults
sys.path.append(str(Path(__file__).parent.parent))
try:
    from src.tools.defaults import DEFAULT_TOOLS_CONFIG
except ImportError:
    print("Error: Could not import DEFAULT_TOOLS_CONFIG from src.tools.defaults")
    sys.exit(1)

def compare_dicts(d1, d2, path=""):
    """Recursively compare two dictionaries and return list of differences."""
    errors = []
    
    # Check keys
    keys1 = set(d1.keys())
    keys2 = set(d2.keys())
    
    for k in keys1 - keys2:
        errors.append(f"Key '{path}{k}' found in tools_config.json but missing in defaults.py")
    for k in keys2 - keys1:
        errors.append(f"Key '{path}{k}' found in defaults.py but missing in tools_config.json")
        
    # Check common keys
    for k in keys1 & keys2:
        v1 = d1[k]
        v2 = d2[k]
        
        if isinstance(v1, dict) and isinstance(v2, dict):
            errors.extend(compare_dicts(v1, v2, f"{path}{k}."))
        elif isinstance(v1, list) and isinstance(v2, list):
            if v1 != v2:
                errors.append(f"Value mismatch at '{path}{k}':\n  JSON: {v1}\n  DEFAULTS: {v2}")
        else:
            if v1 != v2:
                errors.append(f"Value mismatch at '{path}{k}':\n  JSON: {v1}\n  DEFAULTS: {v2}")
                
    return errors

def main():
    json_path = Path("tools_config.json")
    
    if not json_path.exists():
        print(f"Error: {json_path} not found")
        return

    print(f"Comparing {json_path} with src/tools/defaults.py...")
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            config_json = json.load(f)
    except Exception as e:
        print(f"Error loading {json_path}: {e}")
        return

    differences = compare_dicts(config_json, DEFAULT_TOOLS_CONFIG)
    
    if not differences:
        print("\n[SUCCESS] tools_config.json and defaults.py are perfectly synchronized!")
    else:
        print(f"\n[FAILURE] Found {len(differences)} differences:")
        for diff in differences:
            print(f"  - {diff}")
        sys.exit(1)

if __name__ == "__main__":
    main()
