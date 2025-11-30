#!/usr/bin/env python3
"""
API client for calling OpenRouter, Google Gemini, and custom OpenAI-compatible APIs
"""

import base64
import re
import time

import requests

from .config import OPENROUTER_URL
from .utils import is_rate_limit_error, is_insufficient_credits_error, is_invalid_key_error


def call_openrouter_api(key_manager, model, messages, ai_params, timeout):
    """Call OpenRouter API"""
    current_key = key_manager.get_current_key()
    if not current_key:
        return None, "No API key available"
    headers = {
        "Authorization": f"Bearer {current_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
    }
    payload = {"model": model, "messages": messages}
    for param, value in ai_params.items():
        if value is not None:
            payload[param] = value
    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=timeout)
    return response, None


def call_google_api(key_manager, model, messages, ai_params, timeout):
    """Call Google Gemini API"""
    current_key = key_manager.get_current_key()
    if not current_key:
        return None, "No API key available"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"x-goog-api-key": current_key, "Content-Type": "application/json"}
    
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        parts = []
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append({"text": content})
        elif isinstance(content, list):
            for item in content:
                if item.get("type") == "text":
                    parts.append({"text": item.get("text", "")})
                elif item.get("type") == "image_url":
                    url_data = item.get("image_url", {}).get("url", "")
                    if url_data.startswith("data:"):
                        match = re.match(r"data:([^;]+);base64,(.+)", url_data)
                        if match:
                            mime_type, b64_data = match.groups()
                            parts.append({"inline_data": {"mime_type": mime_type, "data": b64_data}})
        contents.append({"role": role, "parts": parts})
    
    payload = {"contents": contents, "generationConfig": {}}
    for param, value in ai_params.items():
        if value is not None:
            payload["generationConfig"][param] = value
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    return response, None


def call_custom_api(key_manager, url, model, messages, ai_params, timeout):
    """Call custom OpenAI-compatible API"""
    current_key = key_manager.get_current_key()
    if not current_key:
        return None, "No API key available"
    headers = {"Authorization": f"Bearer {current_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages}
    for param, value in ai_params.items():
        if value is not None:
            payload[param] = value
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    return response, None


def extract_text_from_response(response_json, provider):
    """Extract text from API response"""
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


def call_api_with_retry(provider, messages, model_override, config, ai_params, key_managers):
    """
    Call API with retry logic and key rotation
    
    Args:
        provider: Provider name (openrouter, google, custom)
        messages: Messages in API format
        model_override: Optional model override
        config: Configuration dictionary
        ai_params: AI parameters dictionary
        key_managers: Dictionary of KeyManager instances
    
    Returns:
        (text, error) tuple
    """
    max_retries = config.get("max_retries", 3)
    retry_delay = config.get("retry_delay", 5)
    timeout = config.get("request_timeout", 120)
    
    key_manager = key_managers.get(provider)
    if not key_manager or not key_manager.has_keys():
        return None, f"No API keys configured for provider: {provider}"
    
    max_attempts = max_retries * max(1, key_manager.get_key_count())
    
    # Determine the model to use
    if model_override:
        model = model_override
    elif provider == "openrouter":
        model = config.get("openrouter_model", "google/gemini-2.5-flash-preview")
    elif provider == "google":
        model = config.get("google_model", "gemini-2.0-flash")
    elif provider == "custom":
        model = config.get("custom_model")
    else:
        model = None
    
    for attempt in range(max_attempts):
        try:
            key_num = key_manager.get_key_number()
            print(f"    Calling {provider} API (key #{key_num}, attempt {attempt + 1}/{max_attempts})")
            print(f"    Model: {model}")
            
            response = None
            error = None
            
            if provider == "openrouter":
                response, error = call_openrouter_api(key_manager, model, messages, ai_params, timeout)
            elif provider == "google":
                response, error = call_google_api(key_manager, model, messages, ai_params, timeout)
            elif provider == "custom":
                url = config.get("custom_url")
                if not url or not model:
                    return None, "Custom API URL or model not configured"
                response, error = call_custom_api(key_manager, url, model, messages, ai_params, timeout)
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
            
            if is_invalid_key_error(response.text, response.status_code):
                print(f"    [Error] Invalid API key #{key_num}")
                new_key = key_manager.rotate_key("(invalid key)")
                if not new_key or not key_manager.has_more_keys():
                    return None, "All API keys are invalid"
                continue
            
            if is_insufficient_credits_error(response.text, resp_json):
                print(f"    [Warning] Insufficient credits on key #{key_num}")
                new_key = key_manager.rotate_key("(insufficient credits)")
                if not new_key or not key_manager.has_more_keys():
                    return None, "All API keys have insufficient credits"
                continue
            
            if response.status_code != 200:
                if is_rate_limit_error(response.text, response.status_code):
                    print(f"    [Warning] Rate limited on key #{key_num}")
                    new_key = key_manager.rotate_key("(rate limited)")
                    if new_key and key_manager.has_more_keys():
                        time.sleep(min(retry_delay, 2))
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


def call_api_simple(provider, prompt, image_base64, mime_type, model_override, config, ai_params, key_managers):
    """Simple API call with image and prompt"""
    data_url = f"data:{mime_type};base64,{image_base64}"
    messages = [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": prompt}
        ]
    }]
    return call_api_with_retry(provider, messages, model_override, config, ai_params, key_managers)


def call_api_chat(session, config, ai_params, key_managers):
    """API call for chat session"""
    messages = session.get_conversation_for_api(include_image=True)
    return call_api_with_retry(session.provider, messages, session.model, config, ai_params, key_managers)
