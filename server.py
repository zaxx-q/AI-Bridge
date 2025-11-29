#!/usr/bin/env python3
"""
Universal ShareX Middleman Server
Supports OpenRouter, Google Gemini, and custom OpenAI-compatible APIs
with smart key rotation, auto-retry, and configurable endpoints.
"""

import base64
import json
import os
import threading
import time
from pathlib import Path

import requests
from flask import Flask, request, abort, jsonify

# Optional: Load .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ============================================================================
# CONFIGURATION DEFAULTS
# ============================================================================

CONFIG_FILE = "config.ini"

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
}

DEFAULT_ENDPOINTS = {
    "ocr": "Extract the text from this image. Preserve the original formatting, including line breaks, spacing, and layout, as accurately as possible. Return only the extracted text.",
    "translate": "Translate all text in this image to English. Preserve the original formatting as much as possible. Return only the translated text.",
    "summarize": "Summarize the content shown in this image concisely. Focus on the main points.",
    "describe": "Describe this image in detail, including all visible elements, text, and context.",
    "code": "Extract any code from this image. Preserve exact formatting, indentation, and syntax. Return only the code.",
}

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Global state
CONFIG = {}
AI_PARAMS = {}
ENDPOINTS = {}
KEY_MANAGERS = {}


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

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
    """Load configuration from INI-style file"""
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
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                continue
            
            # Check for section headers
            if stripped.startswith('[') and stripped.endswith(']'):
                # Save any pending multiline value
                if multiline_key and current_section == 'endpoints':
                    endpoints[multiline_key] = ' '.join(multiline_value)
                    multiline_key = None
                    multiline_value = []
                
                current_section = stripped[1:-1].lower()
                continue
            
            # Parse based on current section
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
                    # Save previous multiline if any
                    if multiline_key:
                        endpoints[multiline_key] = ' '.join(multiline_value)
                    
                    endpoint_name, prompt = stripped.split('=', 1)
                    endpoint_name = endpoint_name.strip().lower()
                    prompt = prompt.strip()
                    
                    if (prompt.startswith('"') and prompt.endswith('"')) or \
                       (prompt.startswith("'") and prompt.endswith("'")):
                        prompt = prompt[1:-1]
                    
                    # Check if this might be a multiline prompt
                    if prompt.endswith('\\'):
                        multiline_key = endpoint_name
                        multiline_value = [prompt[:-1].strip()]
                    else:
                        endpoints[endpoint_name] = prompt
                        multiline_key = None
                        multiline_value = []
                elif multiline_key:
                    # Continuation of multiline
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
        
        # Save final multiline if any
        if multiline_key and current_section == 'endpoints':
            endpoints[multiline_key] = ' '.join(multiline_value)
        
        # Environment variable fallbacks
        if not keys["google"] and os.getenv("GEMINI_API_KEY"):
            keys["google"].append(os.getenv("GEMINI_API_KEY"))
        if not keys["openrouter"] and os.getenv("OPENROUTER_API_KEY"):
            keys["openrouter"].append(os.getenv("OPENROUTER_API_KEY"))
        if not keys["custom"] and os.getenv("CUSTOM_API_KEY"):
            keys["custom"].append(os.getenv("CUSTOM_API_KEY"))
        
    except Exception as e:
        print(f"[Error] Failed to load config: {e}")
    
    return config, ai_params, endpoints, keys


# ============================================================================
# KEY MANAGER (from reference code)
# ============================================================================

class KeyManager:
    """Manages API key rotation for handling rate limits"""
    
    def __init__(self, keys, provider_name):
        self.keys = [k for k in keys if k]
        self.current_index = 0
        self.exhausted_keys = set()
        self.provider_name = provider_name
        self.lock = threading.Lock()
        self.rate_limit_reset_times = {}  # Track when rate limits reset per key
    
    def get_current_key(self):
        with self.lock:
            if not self.keys:
                return None
            if self.current_index >= len(self.keys):
                self.current_index = 0
            return self.keys[self.current_index]
    
    def rotate_key(self, reason=""):
        """Rotate to the next available key"""
        with self.lock:
            if not self.keys:
                return None
            
            self.exhausted_keys.add(self.current_index)
            
            # Find next non-exhausted key
            for i in range(len(self.keys)):
                next_index = (self.current_index + 1 + i) % len(self.keys)
                if next_index not in self.exhausted_keys:
                    self.current_index = next_index
                    print(f"    → Switched to {self.provider_name} key #{self.current_index + 1} {reason}")
                    return self.keys[self.current_index]
            
            # All keys exhausted, reset
            print(f"    → All {self.provider_name} keys exhausted, resetting rotation...")
            self.exhausted_keys.clear()
            self.current_index = 0
            return self.keys[0] if self.keys else None
    
    def mark_rate_limited(self, reset_time=None):
        """Mark current key as rate limited with optional reset time"""
        with self.lock:
            if reset_time:
                self.rate_limit_reset_times[self.current_index] = reset_time
    
    def get_key_count(self):
        return len(self.keys)
    
    def get_key_number(self):
        return self.current_index + 1
    
    def has_keys(self):
        return len(self.keys) > 0
    
    def has_more_keys(self):
        return len(self.exhausted_keys) < len(self.keys)
    
    def reset_exhausted(self):
        with self.lock:
            self.exhausted_keys.clear()


# ============================================================================
# ERROR DETECTION (from reference code)
# ============================================================================

def is_rate_limit_error(error_msg, status_code=None):
    """Check if error is a rate limit error"""
    if status_code == 429:
        return True
    
    error_str = str(error_msg).lower()
    patterns = [
        "too many requests", "rate limit", "rate_limit", "quota exceeded", 
        "429", "throttl", "resource exhausted", "resource_exhausted"
    ]
    return any(p in error_str for p in patterns)


def is_insufficient_credits_error(error_msg, response_json=None):
    """Check if error is an insufficient credits error"""
    error_str = str(error_msg).lower()
    patterns = [
        "insufficient credits", "insufficient funds", "not enough credits",
        "credit balance", "out of credits", "no credits", "payment required",
        "billing", "exceeded your current quota"
    ]
    
    if any(p in error_str for p in patterns):
        return True
    
    if response_json and isinstance(response_json, dict):
        try:
            msg = str(response_json.get("error", {}).get("message", "")).lower()
            if any(p in msg for p in patterns):
                return True
        except:
            pass
    
    return False


def is_invalid_key_error(error_msg, status_code=None):
    """Check if error indicates an invalid API key"""
    if status_code in [401, 403]:
        return True
    
    error_str = str(error_msg).lower()
    patterns = [
        "invalid api key", "invalid key", "api key invalid",
        "unauthorized", "authentication", "forbidden", "not authorized"
    ]
    return any(p in error_str for p in patterns)


# ============================================================================
# API CALLERS
# ============================================================================

def call_openrouter_api(key_manager, model, prompt, image_base64, mime_type, ai_params, timeout):
    """Call OpenRouter API"""
    current_key = key_manager.get_current_key()
    if not current_key:
        return None, "No API key available"
    
    headers = {
        "Authorization": f"Bearer {current_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",  # Required by OpenRouter
    }
    
    data_url = f"data:{mime_type};base64,{image_base64}"
    
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}}
            ]
        }]
    }
    
    for param, value in ai_params.items():
        if value is not None:
            payload[param] = value
    
    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=timeout)
    return response, None


def call_google_api(key_manager, model, prompt, image_base64, mime_type, ai_params, timeout):
    """Call Google Gemini API"""
    current_key = key_manager.get_current_key()
    if not current_key:
        return None, "No API key available"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    
    headers = {
        "x-goog-api-key": current_key,
        "Content-Type": "application/json"
    }
    
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": image_base64}}
            ]
        }],
        "generationConfig": {}
    }
    
    for param, value in ai_params.items():
        if value is not None:
            payload["generationConfig"][param] = value
    
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    return response, None


def call_custom_api(key_manager, url, model, prompt, image_base64, mime_type, ai_params, timeout):
    """Call custom OpenAI-compatible API"""
    current_key = key_manager.get_current_key()
    if not current_key:
        return None, "No API key available"
    
    headers = {
        "Authorization": f"Bearer {current_key}",
        "Content-Type": "application/json"
    }
    
    data_url = f"data:{mime_type};base64,{image_base64}"
    
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}}
            ]
        }]
    }
    
    for param, value in ai_params.items():
        if value is not None:
            payload[param] = value
    
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    return response, None


def extract_text_from_response(response_json, provider):
    """Extract text content from API response based on provider"""
    try:
        if provider in ["openrouter", "custom"]:
            choices = response_json.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                content = message.get("content", "")
                if content:
                    return content
        
        elif provider == "google":
            candidates = response_json.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if parts:
                    return parts[0].get("text", "")
        
        return None
    except Exception as e:
        print(f"    [Error] Failed to extract text: {e}")
        return None


# ============================================================================
# MAIN API CALLER WITH RETRY LOGIC
# ============================================================================

def call_api_with_retry(provider, prompt, image_base64, mime_type):
    """Call the appropriate API with retry logic and key rotation"""
    global CONFIG, AI_PARAMS, KEY_MANAGERS
    
    max_retries = CONFIG.get("max_retries", 3)
    retry_delay = CONFIG.get("retry_delay", 5)
    timeout = CONFIG.get("request_timeout", 120)
    
    key_manager = KEY_MANAGERS.get(provider)
    if not key_manager or not key_manager.has_keys():
        return None, f"No API keys configured for provider: {provider}"
    
    max_attempts = max_retries * max(1, key_manager.get_key_count())
    
    for attempt in range(max_attempts):
        try:
            key_num = key_manager.get_key_number()
            print(f"    Calling {provider} API (key #{key_num}, attempt {attempt + 1}/{max_attempts})")
            
            response = None
            error = None
            
            if provider == "openrouter":
                model = CONFIG.get("openrouter_model", "google/gemini-2.5-flash-preview")
                response, error = call_openrouter_api(
                    key_manager, model, prompt, image_base64, mime_type, AI_PARAMS, timeout
                )
            
            elif provider == "google":
                model = CONFIG.get("google_model", "gemini-2.0-flash")
                response, error = call_google_api(
                    key_manager, model, prompt, image_base64, mime_type, AI_PARAMS, timeout
                )
            
            elif provider == "custom":
                url = CONFIG.get("custom_url")
                model = CONFIG.get("custom_model")
                if not url or not model:
                    return None, "Custom API URL or model not configured"
                response, error = call_custom_api(
                    key_manager, url, model, prompt, image_base64, mime_type, AI_PARAMS, timeout
                )
            
            else:
                return None, f"Unknown provider: {provider}"
            
            if error:
                print(f"    [Error] {error}")
                continue
            
            if response is None:
                continue
            
            resp_json = None
            try:
                resp_json = response.json()
            except:
                pass
            
            # Check for invalid key
            if is_invalid_key_error(response.text, response.status_code):
                print(f"    [Error] Invalid API key #{key_num}")
                new_key = key_manager.rotate_key("(invalid key)")
                if not new_key or not key_manager.has_more_keys():
                    return None, "All API keys are invalid"
                continue
            
            # Check for insufficient credits
            if is_insufficient_credits_error(response.text, resp_json):
                print(f"    [Warning] Insufficient credits on key #{key_num}")
                new_key = key_manager.rotate_key("(insufficient credits)")
                if not new_key or not key_manager.has_more_keys():
                    return None, "All API keys have insufficient credits"
                continue
            
            # Check for rate limiting
            if response.status_code != 200:
                if is_rate_limit_error(response.text, response.status_code):
                    print(f"    [Warning] Rate limited on key #{key_num}")
                    new_key = key_manager.rotate_key("(rate limited)")
                    if new_key and key_manager.has_more_keys():
                        time.sleep(min(retry_delay, 2))  # Short delay when switching keys
                        continue
                    else:
                        print(f"    All keys rate limited, waiting {retry_delay * 2}s...")
                        time.sleep(retry_delay * 2)
                        key_manager.reset_exhausted()
                        continue
                
                print(f"    [Error] API error {response.status_code}: {response.text[:300]}")
                if attempt < max_attempts - 1:
                    time.sleep(retry_delay)
                continue
            
            # Success!
            text = extract_text_from_response(resp_json, provider)
            if text:
                return text, None
            else:
                print(f"    [Warning] No text in response, retrying...")
                if attempt < max_attempts - 1:
                    time.sleep(retry_delay)
                continue
        
        except requests.exceptions.Timeout:
            print(f"    [Error] Request timeout after {timeout}s")
            if attempt < max_attempts - 1:
                time.sleep(retry_delay)
        
        except requests.exceptions.RequestException as e:
            print(f"    [Error] Request failed: {e}")
            if is_rate_limit_error(str(e)):
                key_manager.rotate_key("(rate limit exception)")
            if attempt < max_attempts - 1:
                time.sleep(retry_delay)
        
        except Exception as e:
            print(f"    [Error] Unexpected: {e}")
            if attempt < max_attempts - 1:
                time.sleep(retry_delay)
    
    return None, f"All {max_attempts} attempts failed"


# ============================================================================
# FLASK APPLICATION
# ============================================================================

app = Flask(__name__)


def create_endpoint_handler(endpoint_name, prompt_template):
    """Factory function to create endpoint handlers"""
    
    def handler():
        start_time = time.time()
        
        # Get image from request
        image_bytes = None
        mime_type = 'image/png'
        
        if 'image' in request.files:
            image_file = request.files['image']
            image_bytes = image_file.read()
            mime_type = image_file.mimetype or 'image/png'
        elif request.content_type and 'image' in request.content_type:
            image_bytes = request.get_data()
            mime_type = request.content_type.split(';')[0]
        elif request.data:
            # Try to use raw data as image
            image_bytes = request.data
        
        if not image_bytes:
            abort(400, description='No image found in request. Send as form-data with key "image" or as raw body.')
        
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        # Determine provider (can be overridden)
        provider = CONFIG.get("default_provider", "google")
        if request.args.get('provider'):
            provider = request.args.get('provider').lower()
        elif request.headers.get('X-API-Provider'):
            provider = request.headers.get('X-API-Provider').lower()
        
        # Allow custom prompt override
        prompt = prompt_template
        if request.args.get('prompt'):
            prompt = request.args.get('prompt')
        elif request.headers.get('X-Custom-Prompt'):
            prompt = request.headers.get('X-Custom-Prompt')
        
        print(f"\n{'='*60}")
        print(f"[{endpoint_name.upper()}] New request")
        print(f"  Provider: {provider}")
        print(f"  Image size: {len(image_bytes) / 1024:.1f} KB")
        print(f"  Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
        
        # Call API
        result, error = call_api_with_retry(provider, prompt, base64_image, mime_type)
        
        elapsed = time.time() - start_time
        
        if error:
            print(f"  [FAILED] {error} ({elapsed:.1f}s)")
            print(f"{'='*60}\n")
            return jsonify({"error": error, "elapsed": elapsed}), 500
        
        print(f"  [SUCCESS] {len(result)} chars ({elapsed:.1f}s)")
        print(f"{'='*60}\n")
        
        # Return format based on Accept header
        if request.headers.get('Accept') == 'application/json':
            return jsonify({"text": result, "elapsed": elapsed})
        
        return result, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    
    handler.__name__ = f"handle_{endpoint_name}"
    return handler


@app.route('/')
def index():
    """Show available endpoints and status"""
    available_providers = [p for p, km in KEY_MANAGERS.items() if km.has_keys()]
    
    return jsonify({
        "service": "Universal ShareX Middleman",
        "status": "running",
        "default_provider": CONFIG.get("default_provider", "google"),
        "available_providers": available_providers,
        "endpoints": {f"/{name}": prompt[:100] + "..." if len(prompt) > 100 else prompt 
                     for name, prompt in ENDPOINTS.items()},
        "usage": {
            "method": "POST",
            "body": "multipart/form-data with 'image' field OR raw image bytes",
            "optional_params": {
                "provider": "Override default provider (query param or X-API-Provider header)",
                "prompt": "Override endpoint prompt (query param or X-Custom-Prompt header)"
            }
        }
    })


@app.route('/health')
def health():
    """Health check endpoint"""
    available_providers = {p: km.get_key_count() for p, km in KEY_MANAGERS.items() if km.has_keys()}
    
    return jsonify({
        "status": "healthy",
        "providers": available_providers,
        "endpoints_count": len(ENDPOINTS)
    })


@app.route('/config')
def show_config():
    """Show current configuration (without sensitive data)"""
    safe_config = {k: v for k, v in CONFIG.items() if 'key' not in k.lower() and 'secret' not in k.lower()}
    
    return jsonify({
        "config": safe_config,
        "ai_params": AI_PARAMS,
        "endpoints": list(ENDPOINTS.keys()),
        "providers": {p: km.get_key_count() for p, km in KEY_MANAGERS.items()}
    })


@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": str(e.description)}), 400


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500


# ============================================================================
# INITIALIZATION
# ============================================================================

def initialize():
    """Initialize configuration and register endpoints"""
    global CONFIG, AI_PARAMS, ENDPOINTS, KEY_MANAGERS
    
    print("=" * 60)
    print("Universal ShareX Middleman Server")
    print("=" * 60)
    
    print(f"\nLoading configuration from '{CONFIG_FILE}'...")
    config, ai_params, endpoints, keys = load_config()
    
    CONFIG = config
    AI_PARAMS = ai_params
    ENDPOINTS = endpoints
    
    # Initialize key managers
    for provider in ["custom", "openrouter", "google"]:
        KEY_MANAGERS[provider] = KeyManager(keys[provider], provider)
        count = len(keys[provider])
        if count > 0:
            print(f"  ✓ {provider}: {count} API key(s) loaded")
        else:
            print(f"  ✗ {provider}: No API keys")
    
    print(f"\nServer Configuration:")
    print(f"  Host: {CONFIG.get('host', '127.0.0.1')}")
    print(f"  Port: {CONFIG.get('port', 5000)}")
    print(f"  Default Provider: {CONFIG.get('default_provider', 'google')}")
    print(f"  Max Retries: {CONFIG.get('max_retries', 3)}")
    print(f"  Request Timeout: {CONFIG.get('request_timeout', 120)}s")
    
    if AI_PARAMS:
        print(f"\nAI Parameters:")
        for k, v in AI_PARAMS.items():
            print(f"  {k}: {v}")
    
    print(f"\nRegistering {len(ENDPOINTS)} endpoint(s):")
    for endpoint_name, prompt in ENDPOINTS.items():
        handler = create_endpoint_handler(endpoint_name, prompt)
        app.add_url_rule(f'/{endpoint_name}', endpoint_name, handler, methods=['POST'])
        prompt_preview = prompt[:60] + "..." if len(prompt) > 60 else prompt
        print(f"  /{endpoint_name}")
        print(f"      → {prompt_preview}")
    
    print("\n" + "=" * 60)


def generate_example_config():
    """Generate an example config.ini file"""
    return '''# ============================================================
# Universal ShareX Middleman Server Configuration
# ============================================================

[config]
# Server settings
host = 127.0.0.1
port = 5000

# Default API provider: custom, openrouter, or google
default_provider = google

# Custom API configuration (for OpenAI-compatible APIs)
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

# AI Parameters (optional - uncomment to use)
# temperature = 0.7
# max_tokens = 4096
# top_p = 1.0

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

explain_code = Extract and explain any code shown in this image. First show the code, then explain what it does.

latex = Convert any mathematical equations or formulas in this image to LaTeX format. Return only the LaTeX code.

markdown = Convert the content of this image to Markdown format. Preserve the structure, headings, lists, and formatting.

proofread = Extract the text from this image and proofread it. Fix any spelling, grammar, or punctuation errors. Return the corrected text.

caption = Generate a short, descriptive caption for this image suitable for social media or alt text.

analyze = Analyze this image and provide insights about its content, context, and any notable elements.

extract_data = Extract any structured data (tables, lists, key-value pairs) from this image and format it clearly.

handwriting = Transcribe any handwritten text in this image as accurately as possible.
'''


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    # Create example config if it doesn't exist
    if not Path(CONFIG_FILE).exists():
        print(f"Config file '{CONFIG_FILE}' not found.")
        print("Creating example configuration file...")
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write(generate_example_config())
        print(f"✓ Created '{CONFIG_FILE}'")
        print("\nPlease edit the config file to add your API keys, then restart.")
        print("At minimum, you need to add at least one API key in the")
        print("[google], [openrouter], or [custom] section.")
        exit(0)
    
    # Initialize configuration
    initialize()
    
    # Check if any API keys are configured
    has_any_keys = any(km.has_keys() for km in KEY_MANAGERS.values())
    if not has_any_keys:
        print("\n⚠️  WARNING: No API keys configured!")
        print("Please add your API keys to config.ini")
        print("\nAlternatively, set environment variables:")
        print("  - GEMINI_API_KEY for Google Gemini")
        print("  - OPENROUTER_API_KEY for OpenRouter")
        print("  - CUSTOM_API_KEY for custom APIs")
        print("\nThe server will start but all requests will fail.\n")
    
    # Start server
    host = CONFIG.get('host', '127.0.0.1')
    port = int(CONFIG.get('port', 5000))
    
    print(f"\n🚀 Starting server at http://{host}:{port}")
    print(f"   Available endpoints: {', '.join('/' + e for e in ENDPOINTS.keys())}")
    print("\nPress Ctrl+C to stop\n")
    
    app.run(host=host, port=port, debug=False, threaded=True)