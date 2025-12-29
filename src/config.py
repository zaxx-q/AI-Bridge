#!/usr/bin/env python3
"""
Configuration loading and management
"""

import os
from pathlib import Path

# Configuration file paths
CONFIG_FILE = "config.ini"
SESSIONS_FILE = "chat_sessions.json"

# Default configuration
DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 5000,
    "default_provider": "google",
    # Custom URL: If it contains "google" or "googleapis.com",
    # Google-specific behavior is automatically applied
    "custom_url": None,
    "custom_model": None,
    "openrouter_model": "openai/gpt-oss-120b:free",
    "google_model": "gemma-3-27b-it",
    "max_retries": 3,
    "retry_delay": 5,
    "request_timeout": 120,
    "max_sessions": 50,
    # Show AI response in chat window: yes or no
    # This controls whether responses appear in a GUI window or are typed directly.
    # For API endpoints: overridden by ?show=yes/no URL parameter
    # For TextEditTool: overridden by show_chat_window_instead_of_replace per-action setting,
    #                   which is further overridden by popup radio button selection
    "show_ai_response_in_chat_window": "no",
    # Legacy alias for backward compatibility
    "default_show": "no",
    # Streaming and thinking settings
    "streaming_enabled": True,
    "thinking_enabled": False,
    "thinking_output": "reasoning_content",  # filter, raw, or reasoning_content
    # Thinking configuration (per JSON-request-reference.md)
    # - reasoning_effort: For OpenAI-compatible APIs ("low", "medium", "high")
    # - thinking_budget: For Gemini 2.5 models (integer tokens, -1 = auto/unlimited)
    # - thinking_level: For Gemini 3.x models ("low", "high")
    "reasoning_effort": "high",
    "thinking_budget": -1,
    "thinking_level": "high",
    # TextEditTool settings
    "text_edit_tool_enabled": True,
    "text_edit_tool_hotkey": "ctrl+space",
    # Hotkey to abort streaming typing (default: escape)
    "text_edit_tool_abort_hotkey": "escape",
    # Delay between characters when streaming to text field (ms)
    # Lower = faster typing. Default: 5
    "streaming_typing_delay": 5,
    # Uncap typing speed - type at maximum speed from server stream
    # WARNING: May cause issues with some applications (input lag, missed characters)
    "streaming_typing_uncapped": False,
    # UI Theme settings
    # Available themes: catppuccin, dracula, nord, gruvbox, onedark, minimal, highcontrast
    "ui_theme": "catppuccin",
    # Theme mode: auto (follows system), dark, light
    "ui_theme_mode": "auto",
}

# Default endpoint definitions
DEFAULT_ENDPOINTS = {
    "ocr": "Extract the text from this image. Preserve the original formatting, including line breaks, spacing, and layout, as accurately as possible. Return only the extracted text.",
    "ocr_translate": "Extract all text from this image and translate it to {lang}. Preserve the original formatting as much as possible. Return only the translated text.",
    "translate": "Translate all text in this image to English. Preserve the original formatting as much as possible. Return only the translated text.",
    "summarize": "Summarize the content shown in this image concisely. Focus on the main points.",
    "describe": "Describe this image in detail, including all visible elements, text, and context.",
    "code": "Extract any code from this image. Preserve exact formatting, indentation, and syntax. Return only the code.",
}

# API URLs
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def parse_config_value(value_str):
    """Parse a configuration value from string to appropriate type"""
    value_str = value_str.strip()
    if value_str.lower() in ['none', 'null', '']:
        return None
    if value_str.lower() in ['true', 'yes', 'on', '1']:
        return True
    if value_str.lower() in ['false', 'no', 'off', '0']:
        return False
    try:
        if '.' not in value_str:
            return int(value_str)
        return float(value_str)
    except ValueError:
        pass
    if (value_str.startswith('"') and value_str.endswith('"')) or \
       (value_str.startswith("'") and value_str.endswith("'")):
        return value_str[1:-1]
    return value_str


def load_config(filepath=CONFIG_FILE):
    """Load configuration from .ini file"""
    config = dict(DEFAULT_CONFIG)
    ai_params = {}
    endpoints = dict(DEFAULT_ENDPOINTS)
    keys = {"custom": [], "openrouter": [], "google": []}
    
    if not Path(filepath).exists():
        print(f"[Warning] Config file '{filepath}' not found. Using defaults.")
        return config, ai_params, endpoints, keys
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        current_section = None
        multiline_key = None
        multiline_value = []
        
        for line in lines:
            raw_line = line.rstrip('\n\r')
            stripped = raw_line.strip()
            
            if not stripped or stripped.startswith('#'):
                continue
            
            if stripped.startswith('[') and stripped.endswith(']'):
                if multiline_key and current_section == 'endpoints':
                    endpoints[multiline_key] = ' '.join(multiline_value)
                    multiline_key = None
                    multiline_value = []
                current_section = stripped[1:-1].lower()
                continue
            
            if current_section == 'config':
                if '=' in stripped:
                    key, value = stripped.split('=', 1)
                    key = key.strip().lower()
                    value = parse_config_value(value)
                    if key in DEFAULT_CONFIG:
                        config[key] = value
                    elif value is not None:
                        ai_params[key] = value
            
            elif current_section == 'endpoints':
                if '=' in stripped:
                    if multiline_key:
                        endpoints[multiline_key] = ' '.join(multiline_value)
                    endpoint_name, prompt = stripped.split('=', 1)
                    endpoint_name = endpoint_name.strip().lower()
                    prompt = prompt.strip()
                    if (prompt.startswith('"') and prompt.endswith('"')) or \
                       (prompt.startswith("'") and prompt.endswith("'")):
                        prompt = prompt[1:-1]
                    if prompt.endswith('\\'):
                        multiline_key = endpoint_name
                        multiline_value = [prompt[:-1].strip()]
                    else:
                        endpoints[endpoint_name] = prompt
                        multiline_key = None
                        multiline_value = []
                elif multiline_key:
                    if stripped.endswith('\\'):
                        multiline_value.append(stripped[:-1].strip())
                    else:
                        multiline_value.append(stripped)
                        endpoints[multiline_key] = ' '.join(multiline_value)
                        multiline_key = None
                        multiline_value = []
            
            elif current_section in keys:
                if stripped and not stripped.startswith('#'):
                    keys[current_section].append(stripped)
        
        if multiline_key and current_section == 'endpoints':
            endpoints[multiline_key] = ' '.join(multiline_value)
        
        # Load from environment variables if not in config
        if not keys["google"] and os.getenv("GEMINI_API_KEY"):
            keys["google"].append(os.getenv("GEMINI_API_KEY"))
        if not keys["openrouter"] and os.getenv("OPENROUTER_API_KEY"):
            keys["openrouter"].append(os.getenv("OPENROUTER_API_KEY"))
        if not keys["custom"] and os.getenv("CUSTOM_API_KEY"):
            keys["custom"].append(os.getenv("CUSTOM_API_KEY"))
        
    except Exception as e:
        print(f"[Error] Failed to load config: {e}")
    
    return config, ai_params, endpoints, keys


def save_config_value(key: str, value, filepath=CONFIG_FILE):
    """Update a single config value in the config file"""
    try:
        if not Path(filepath).exists():
            return False
        
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Convert value to string
        if isinstance(value, bool):
            value_str = "true" if value else "false"
        elif value is None:
            value_str = "none"
        else:
            value_str = str(value)
        
        # Find and update the key in [config] section
        in_config_section = False
        found = False
        new_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            # Track section
            if stripped.startswith('[') and stripped.endswith(']'):
                in_config_section = stripped.lower() == '[config]'
            
            # Update key if in config section
            if in_config_section and stripped.startswith(f"{key} =") or stripped.startswith(f"{key}="):
                new_lines.append(f"{key} = {value_str}\n")
                found = True
            else:
                new_lines.append(line)
        
        # If not found, add it to [config] section
        if not found:
            final_lines = []
            added = False
            for line in new_lines:
                final_lines.append(line)
                if not added and line.strip().lower() == '[config]':
                    final_lines.append(f"{key} = {value_str}\n")
                    added = True
            new_lines = final_lines
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        return True
    except Exception as e:
        print(f"[Error] Failed to save config: {e}")
        return False


def generate_example_config():
    """Generate example configuration file content"""
    return '''# ============================================================
# AI Bridge - Multi-modal AI Assistant Server Configuration
# ============================================================

[config]
# Server settings
host = 127.0.0.1
port = 5000

# Default API provider: custom, openrouter, or google
default_provider = google

# ============================================================
# RESPONSE DISPLAY SETTINGS
# ============================================================
# Show AI response in a chat window (yes) or type directly (no)
#
# Override hierarchy (highest to lowest priority):
#   1. ?show=yes/no URL parameter (API endpoints only)
#   2. Popup radio button selection (TextEditTool, if not "Default")
#   3. show_chat_window_instead_of_replace per-action setting (TextEditTool)
#   4. This global setting (show_ai_response_in_chat_window)
show_ai_response_in_chat_window = no

# Custom API configuration
# custom_url = https://api.openai.com/v1/chat/completions
# custom_model = gpt-5.1
#
# NOTE: If custom_url contains "google" or "googleapis.com", the system will
# automatically apply Google-specific settings (safety_settings, thinking_config).
# Example for Google's OpenAI-compatible endpoint:
# custom_url = https://generativelanguage.googleapis.com/v1beta/openai
# custom_model = gemini-2.5-flash

# OpenRouter model (see https://openrouter.ai/models for options)
openrouter_model = openai/gpt-oss-120b:free

# Google Gemini model
google_model = gemma-3-27b-it

# Retry settings
max_retries = 3
retry_delay = 5
request_timeout = 120

# Session management
max_sessions = 50

# AI Parameters (optional)
# temperature = 0.7
# max_tokens = 4096
# top_p = 1.0

# ============================================================
# STREAMING AND THINKING SETTINGS
# ============================================================
# Enable streaming responses (default: true)
streaming_enabled = true

# Enable extended thinking/reasoning mode (default: false)
thinking_enabled = false

# How to handle thinking output: filter, raw, or reasoning_content
# - filter: Hide thinking content
# - raw: Include thinking in main response
# - reasoning_content: Separate field (for collapsible display)
thinking_output = reasoning_content

# Thinking configuration (for different providers)
# - reasoning_effort: OpenAI-compatible APIs (low, medium, high)
# - thinking_budget: Gemini 2.5 models (integer tokens, -1 = auto/unlimited)
# - thinking_level: Gemini 3.x models (low, high)
reasoning_effort = high
thinking_budget = -1
thinking_level = high

# ============================================================
# TEXT EDIT TOOL - Hotkey-triggered text processing with AI
# ============================================================
# Enable/disable TextEditTool
text_edit_tool_enabled = true

# Hotkey combination (e.g., ctrl+space, ctrl+alt+w)
text_edit_tool_hotkey = ctrl+space

# Hotkey to abort streaming typing (default: escape)
# Press this key to stop mid-stream typing
text_edit_tool_abort_hotkey = escape

# Delay between characters when streaming to text field (milliseconds)
# Lower = faster typing. Default: 5
streaming_typing_delay = 5

# Uncap typing speed - type at maximum speed from server stream
# WARNING: Setting to true may cause issues with some applications
# (input lag, missed characters, application freezing). Use with caution!
# streaming_typing_uncapped = false

# TextEditTool options are configured in text_edit_tool_options.json
# including: action prompts, placeholders, and per-action display settings

# ============================================================
# UI THEME SETTINGS
# ============================================================
# Available themes: catppuccin, dracula, nord, gruvbox, onedark, minimal, highcontrast
ui_theme = catppuccin

# Theme mode: auto (follows system dark/light), dark, light
ui_theme_mode = auto


# ============================================================
# API KEYS - Add your keys below (one per line)
# You can add multiple keys for automatic rotation on rate limits
# ============================================================

[custom]
# Your custom/OpenAI API keys here (one per line)
# sk-xxxxxxxxxxxxxxxxxxxxx
# sk-yyyyyyyyyyyyyyyyyyyyy

[openrouter]
# Your OpenRouter API keys here (one per line)
# sk-or-v1-xxxxxxxxxxxxxxxxxxxxx

[google]
# Your Google Gemini API keys here (one per line)
# Get keys at: https://aistudio.google.com/app/apikey
# AIzaSyXXXXXXXXXXXXXXXXXXXXXXX

[endpoints]
# ============================================================
# ENDPOINTS - Define your custom endpoints and prompts
# Format: endpoint_name = prompt text
# Access via: POST http://host:port/endpoint_name
# ============================================================

# Use {lang} placeholder for dynamic language - pass ?lang=Japanese, ?lang=Indonesian, etc.
ocr = Extract the text from this image. Preserve the original formatting, including line breaks, spacing, and layout, as accurately as possible. Return only the extracted text.

ocr_translate = Extract all text from this image and translate it to {lang}. Preserve the original formatting as much as possible. Return only the translated text.

translate = Translate all text in this image to English. Preserve the original formatting as much as possible. Return only the translated text.

translate_ja = Translate all Japanese text in this image to English. Maintain the original structure and formatting. Return only the translation.

translate_zh = Translate all Chinese text in this image to English. Maintain the original structure and formatting. Return only the translation.

translate_ko = Translate all Korean text in this image to English. Maintain the original structure and formatting. Return only the translation.

summarize = Summarize the content shown in this image concisely. Focus on the main points and key information.

describe = Describe this image in detail, including all visible elements, text, colors, and context.

code = Extract any code from this image. Preserve exact formatting, indentation, and syntax. Return only the code without any explanation.

explain = Analyze and explain what is shown in this image. Provide context and insights.

explain_code = Extract and explain any code shown in this image. First show the code, then explain what it does.

latex = Convert any mathematical equations or formulas in this image to LaTeX format. Return only the LaTeX code.

markdown = Convert the content of this image to Markdown format. Preserve the structure, headings, lists, and formatting.

proofread = Extract the text from this image and proofread it. Fix any spelling, grammar, or punctuation errors. Return the corrected text.

caption = Generate a short, descriptive caption for this image suitable for social media or alt text.

analyze = Analyze this image and provide insights about its content, context, and any notable elements.

extract_data = Extract any structured data (tables, lists, key-value pairs) from this image and format it clearly.

handwriting = Transcribe any handwritten text in this image as accurately as possible.
'''


