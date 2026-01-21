#!/usr/bin/env python3
"""
Tools Configuration Loader

Loads and manages tools_config.json configuration.
Creates the config file on-demand when user first interacts with tools.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List

from .defaults import DEFAULT_TOOLS_CONFIG

TOOLS_CONFIG_FILE = "tools_config.json"


def get_default_config() -> Dict[str, Any]:
    """
    Get default tools configuration.
    
    Returns:
        Default configuration dictionary from defaults.py
    """
    return DEFAULT_TOOLS_CONFIG.copy()


def ensure_tools_config(filepath: str = TOOLS_CONFIG_FILE) -> Path:
    """
    Ensure tools_config.json exists, creating it from defaults if needed.
    
    This should be called when user first interacts with tools,
    NOT at application startup.
    
    Args:
        filepath: Path to tools_config.json
    
    Returns:
        Path to the config file
    """
    path = Path(filepath)
    
    if not path.exists():
        print(f"[Info] Creating default tools config: {filepath}")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_TOOLS_CONFIG, f, indent=2, ensure_ascii=False)
            print(f"[Success] Created {filepath}")
        except IOError as e:
            print(f"[Error] Failed to create tools config: {e}")
    
    return path


def load_tools_config(filepath: str = TOOLS_CONFIG_FILE, create_if_missing: bool = True) -> Dict[str, Any]:
    """
    Load tools configuration from JSON file.
    
    Args:
        filepath: Path to tools_config.json
        create_if_missing: If True, create the file from defaults when missing
    
    Returns:
        Configuration dictionary
    """
    path = Path(filepath)
    
    if not path.exists():
        if create_if_missing:
            ensure_tools_config(filepath)
        else:
            return get_default_config()
    
    # Re-check after potential creation
    if not path.exists():
        return get_default_config()
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[Error] Failed to load tools config: {e}")
        return get_default_config()


def get_file_processor_prompts(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Get file processor prompts from config.
    
    Args:
        config: Tools configuration dictionary
    
    Returns:
        Dictionary of prompt name -> prompt config
    """
    return config.get("file_processor", {}).get("prompts", {})


def get_prompt_by_key(config: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific prompt configuration.
    
    Args:
        config: Tools configuration dictionary
        key: Prompt key name
    
    Returns:
        Prompt configuration or None
    """
    prompts = get_file_processor_prompts(config)
    return prompts.get(key)


def get_setting(config: Dict[str, Any], key: str, default: Any = None) -> Any:
    """
    Get a setting from _settings section.
    
    Args:
        config: Tools configuration dictionary
        key: Setting key
        default: Default value if not found
    
    Returns:
        Setting value
    """
    return config.get("_settings", {}).get(key, default)


def get_file_type_mappings(config: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Get file type mappings from config.
    
    Args:
        config: Tools configuration dictionary
    
    Returns:
        Dictionary of file type -> list of extensions
    """
    return config.get("file_processor", {}).get("file_type_mappings", {})


def resolve_endpoint_prompt(prompt_text: str, endpoints: Dict[str, str]) -> str:
    """
    Resolve @endpoint:name references in prompt text.
    
    Args:
        prompt_text: Prompt text that may contain @endpoint:name
        endpoints: Dictionary of endpoint name -> prompt
    
    Returns:
        Resolved prompt text
    """
    if prompt_text.startswith("@endpoint:"):
        endpoint_name = prompt_text[10:].strip()  # Remove "@endpoint:"
        if endpoint_name in endpoints:
            return endpoints[endpoint_name]
        else:
            print(f"[Warning] Endpoint '{endpoint_name}' not found")
            return prompt_text
    return prompt_text


def list_available_prompts(
    config: Dict[str, Any],
    endpoints: Dict[str, str] = None,
    filter_input_type: str = None
) -> List[Dict[str, Any]]:
    """
    List all available prompts for file processor.
    
    Args:
        config: Tools configuration dictionary
        endpoints: Optional endpoints dict to include endpoint prompts
        filter_input_type: Optional filter by input type (image, text, code)
    
    Returns:
        List of prompt info dicts with keys: key, icon, description, input_types
    """
    result = []
    prompts = get_file_processor_prompts(config)
    
    # Add tool prompts
    for key, prompt_config in prompts.items():
        if key.startswith("_"):
            continue  # Skip internal prompts
        
        input_types = prompt_config.get("input_types", ["image", "text", "code"])
        
        # Apply filter if specified
        if filter_input_type and filter_input_type not in input_types:
            continue
        
        result.append({
            "key": key,
            "icon": prompt_config.get("icon", "📄"),
            "description": prompt_config.get("description", ""),
            "input_types": input_types,
            "source": "tool"
        })
    
    # Add endpoint prompts if provided
    if endpoints:
        for name, prompt in endpoints.items():
            result.append({
                "key": f"@endpoint:{name}",
                "icon": "📡",
                "description": f"Endpoint: {prompt[:50]}..." if len(prompt) > 50 else f"Endpoint: {prompt}",
                "input_types": ["image"],  # Endpoints are typically for images
                "source": "endpoint"
            })
    
    return result