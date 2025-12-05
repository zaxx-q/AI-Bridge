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
    "custom_url": None,
    "custom_model": None,
    "openrouter_model": "google/gemini-2.5-flash-preview",
    "google_model": "gemini-2.0-flash",
    "max_retries": 3,
    "retry_delay": 5,
    "request_timeout": 120,
    "max_sessions": 50,
    "default_show": "no",
    # TextEditTool settings
    "text_edit_tool_enabled": True,
    "text_edit_tool_hotkey": "ctrl+space",
    "text_edit_tool_response_mode": "replace",  # "replace" or "popup"
}

# Default endpoint definitions
DEFAULT_ENDPOINTS = {
    "ocr": "Extract the text from this image. Preserve the original formatting, including line breaks, spacing, and layout, as accurately as possible. Return only the extracted text.",
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

# Show chat window for responses: yes or no
default_show = no

# Custom API configuration
# custom_url = https://api.openai.com/v1/chat/completions
# custom_model = gpt-4o

# OpenRouter model (see https://openrouter.ai/models for options)
openrouter_model = google/gemini-2.5-flash-preview

# Google Gemini model
google_model = gemini-2.0-flash

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
# TEXT EDIT TOOL - Hotkey-triggered text processing with AI
# ============================================================
# Enable/disable TextEditTool
text_edit_tool_enabled = true

# Hotkey combination (e.g., ctrl+space, ctrl+alt+w)
text_edit_tool_hotkey = ctrl+space

# Response mode: replace (replace selected text) or popup (show in window)
text_edit_tool_response_mode = replace


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

# ============================================================
# ENDPOINTS - Define your custom endpoints and prompts
# Format: endpoint_name = prompt text
# Access via: POST http://host:port/endpoint_name
# ============================================================

[endpoints]
ocr = Extract the text from this image. Preserve the original formatting, including line breaks, spacing, and layout, as accurately as possible. Return only the extracted text.

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

