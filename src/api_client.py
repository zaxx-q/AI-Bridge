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
    
    payload = {
        "contents": contents, 
        "generationConfig": {},
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "OFF"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "OFF"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "OFF"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "OFF"},
            {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "OFF"}
        ]
    }
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
    
    # Ensure URL ends with /chat/completions
    if not url.endswith("/chat/completions"):
        url = url.rstrip("/") + "/chat/completions"
    
    headers = {"Authorization": f"Bearer {current_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages}
    for param, value in ai_params.items():
        if value is not None:
            payload[param] = value
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    return response, None


def estimate_tokens(text: str) -> int:
    """Estimate token count (roughly 4 characters per token)"""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_message_tokens(messages: list) -> int:
    """Estimate token count for a list of messages"""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for item in content:
                if item.get("type") == "text":
                    total += estimate_tokens(item.get("text", ""))
                elif item.get("type") == "image_url":
                    # Estimate ~85 tokens per image (conservative)
                    total += 85
        # Add overhead for role, etc.
        total += 4
    return total


def call_custom_api_stream(key_manager, url, model, messages, ai_params, timeout, callback, thinking_output="reasoning_content"):
    """
    Call custom OpenAI-compatible API with streaming support.
    
    Args:
        key_manager: Key manager for API keys
        url: API endpoint URL
        model: Model name
        messages: List of messages
        ai_params: AI parameters
        timeout: Request timeout
        callback: Function called with (type, content) for each chunk
                  Types: 'text', 'thinking', 'usage', 'done', 'error'
        thinking_output: How to handle thinking - 'filter', 'raw', 'reasoning_content'
    
    Returns:
        (full_text, reasoning_text, usage_data, error)
    """
    import json
    
    current_key = key_manager.get_current_key()
    if not current_key:
        return None, None, None, "No API key available"
    
    # Ensure URL ends with /chat/completions
    if not url.endswith("/chat/completions"):
        url = url.rstrip("/") + "/chat/completions"
    
    headers = {"Authorization": f"Bearer {current_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "stream": True}
    for param, value in ai_params.items():
        if value is not None:
            payload[param] = value
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout, stream=True)
        
        if response.status_code != 200:
            error_text = response.text[:500]
            return None, None, None, f"API error ({response.status_code}): {error_text}"
        
        full_text = ""
        reasoning_text = ""
        usage_data = None
        in_thinking = False
        text_buffer = ""
        
        # Explicitly set UTF-8 encoding for proper Unicode handling
        response.encoding = 'utf-8'
        
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            if not line.startswith("data: "):
                continue
            
            data_str = line[6:]  # Remove "data: " prefix
            
            if data_str == "[DONE]":
                # Flush any remaining buffer
                if text_buffer:
                    if in_thinking:
                        if thinking_output != "filter":
                            reasoning_text += text_buffer
                            if thinking_output == "raw":
                                callback("text", text_buffer)
                            else:
                                callback("thinking", text_buffer)
                    else:
                        full_text += text_buffer
                        callback("text", text_buffer)
                callback("done", None)
                break
            
            try:
                data = json.loads(data_str)
                choice = data.get("choices", [{}])[0]
                delta = choice.get("delta", {})
                
                # Handle regular content
                content = delta.get("content", "")
                if content:
                    text_buffer += content
                    
                    # Process buffer for <think> tags
                    while True:
                        if not in_thinking:
                            # Look for <think> opening tag
                            think_start = text_buffer.find("<think>")
                            if think_start == -1:
                                # No tag, output safe portion (keep last 7 chars as buffer)
                                if len(text_buffer) > 7:
                                    safe_text = text_buffer[:-7]
                                    text_buffer = text_buffer[-7:]
                                    full_text += safe_text
                                    callback("text", safe_text)
                                break
                            else:
                                # Found <think>, output text before it
                                before_think = text_buffer[:think_start]
                                text_buffer = text_buffer[think_start + 7:]
                                in_thinking = True
                                if before_think:
                                    full_text += before_think
                                    callback("text", before_think)
                        else:
                            # Look for </think> closing tag
                            think_end = text_buffer.find("</think>")
                            if think_end == -1:
                                # No closing tag, output safe portion
                                if len(text_buffer) > 8:
                                    safe_text = text_buffer[:-8]
                                    text_buffer = text_buffer[-8:]
                                    if thinking_output != "filter":
                                        reasoning_text += safe_text
                                        if thinking_output == "raw":
                                            callback("text", safe_text)
                                        else:
                                            callback("thinking", safe_text)
                                break
                            else:
                                # Found </think>, output thinking content
                                thinking_content = text_buffer[:think_end]
                                text_buffer = text_buffer[think_end + 8:]
                                in_thinking = False
                                if thinking_output != "filter" and thinking_content:
                                    reasoning_text += thinking_content
                                    if thinking_output == "raw":
                                        callback("text", thinking_content)
                                    else:
                                        callback("thinking", thinking_content)
                
                # Handle reasoning_content (DeepSeek style)
                reasoning_content = delta.get("reasoning_content", "")
                if reasoning_content:
                    if thinking_output != "filter":
                        reasoning_text += reasoning_content
                        if thinking_output == "raw":
                            callback("text", reasoning_content)
                        else:
                            callback("thinking", reasoning_content)
                
                # Handle usage data
                if "usage" in data:
                    usage = data["usage"]
                    usage_data = {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0)
                    }
                    callback("usage", usage_data)
                    
            except json.JSONDecodeError:
                continue
        
        # If no usage data from API, estimate it
        if not usage_data:
            input_tokens = estimate_message_tokens(messages)
            output_tokens = estimate_tokens(full_text + reasoning_text)
            usage_data = {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "estimated": True
            }
            callback("usage", usage_data)
        
        return full_text, reasoning_text, usage_data, None
        
    except requests.exceptions.Timeout:
        return None, None, None, f"Request timeout after {timeout}s"
    except requests.exceptions.RequestException as e:
        return None, None, None, f"Request failed: {e}"
    except Exception as e:
        return None, None, None, f"Unexpected error: {e}"


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


def call_api_chat_stream(session, config, ai_params, key_managers, callback):
    """
    API call for chat session with streaming support.
    Supports: custom, google (via OpenAI-compat), openrouter
    
    Args:
        session: Chat session object
        config: Configuration dictionary
        ai_params: AI parameters
        key_managers: Dictionary of key managers
        callback: Callback function for streaming updates
                  Called with (type, content) - types: 'text', 'thinking', 'usage', 'done', 'error'
    
    Returns:
        (text, reasoning_text, usage_data, error) tuple
    """
    messages = session.get_conversation_for_api(include_image=True)
    provider = session.provider
    
    key_manager = key_managers.get(provider)
    if not key_manager or not key_manager.has_keys():
        return None, None, None, f"No API keys configured for provider: {provider}"
    
    timeout = config.get("request_timeout", 120)
    thinking_output = config.get("thinking_output", "reasoning_content")
    thinking_enabled = config.get("thinking_enabled", False)
    
    # Determine model
    if session.model:
        model = session.model
    elif provider == "custom":
        model = config.get("custom_model")
    elif provider == "openrouter":
        model = config.get("openrouter_model", "google/gemini-2.5-flash-preview")
    elif provider == "google":
        model = config.get("google_model", "gemini-2.0-flash")
    else:
        model = None
    
    # Build OpenAI-compatible streaming request
    if provider == "custom":
        url = config.get("custom_url")
        if not url or not model:
            return None, None, None, "Custom API URL or model not configured"
        
        # Ensure URL ends with /chat/completions
        if not url.endswith("/chat/completions"):
            url = url.rstrip("/") + "/chat/completions"
        
        # Build extra params for thinking if enabled
        extra_ai_params = dict(ai_params)
        if thinking_enabled:
            extra_ai_params["reasoning_effort"] = "medium"
        
        return call_custom_api_stream(
            key_manager, url, model, messages, extra_ai_params, 
            timeout, callback, thinking_output
        )
    
    elif provider == "google":
        # Use Google's OpenAI-compatible endpoint for streaming
        url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        
        # Build extra params for thinking if enabled
        extra_ai_params = dict(ai_params)
        if thinking_enabled:
            extra_ai_params["reasoning_effort"] = "medium"
        
        return call_custom_api_stream(
            key_manager, url, model, messages, extra_ai_params,
            timeout, callback, thinking_output
        )
    
    elif provider == "openrouter":
        # OpenRouter uses standard OpenAI format
        url = "https://openrouter.ai/api/v1/chat/completions"
        
        return call_custom_api_stream(
            key_manager, url, model, messages, ai_params,
            timeout, callback, thinking_output
        )
    
    else:
        # Fallback to non-streaming
        text, error = call_api_with_retry(provider, messages, session.model, config, ai_params, key_managers)
        if error:
            callback("error", error)
            return None, None, None, error
        
        # Emit the full response as a single chunk
        callback("text", text)
        
        # Estimate tokens for non-streaming response
        usage_data = {
            "prompt_tokens": estimate_message_tokens(messages),
            "completion_tokens": estimate_tokens(text),
            "total_tokens": estimate_message_tokens(messages) + estimate_tokens(text),
            "estimated": True
        }
        callback("usage", usage_data)
        callback("done", None)
        
        return text, "", usage_data, None


def fetch_models(config, key_managers, provider_override=None):
    """
    Fetch available models from the configured API.
    
    Args:
        config: Configuration dictionary
        key_managers: Dictionary of key managers
        provider_override: Optional provider to fetch from (defaults to default_provider)
    
    Returns:
        (models_list, error) tuple
        models_list is a list of dicts with 'id' and 'name' keys
    """
    provider = provider_override or config.get("default_provider", "custom")
    
    if provider == "custom":
        url = config.get("custom_url")
        if not url:
            return None, "Custom API URL not configured"
        
        # Get base URL (remove /chat/completions if present)
        base_url = url.rstrip("/")
        if base_url.endswith("/chat/completions"):
            base_url = base_url[:-17]
        
        models_url = base_url + "/models"
        
        key_manager = key_managers.get("custom")
        if not key_manager or not key_manager.has_keys():
            return None, "No API keys configured for custom provider"
        
        current_key = key_manager.get_current_key()
        if not current_key:
            return None, "No API key available"
        
        headers = {
            "Authorization": f"Bearer {current_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.get(models_url, headers=headers, timeout=30)
            
            if response.status_code != 200:
                return None, f"Failed to fetch models ({response.status_code}): {response.text[:200]}"
            
            data = response.json()
            return _parse_models_response(data)
            
        except requests.exceptions.RequestException as e:
            return None, f"Request failed: {e}"
        except Exception as e:
            return None, f"Error fetching models: {e}"
    
    elif provider == "google":
        # Fetch from Google AI API
        key_manager = key_managers.get("google")
        if not key_manager or not key_manager.has_keys():
            return None, "No API keys configured for Google provider"
        
        current_key = key_manager.get_current_key()
        if not current_key:
            return None, "No API key available"
        
        # Google models endpoint
        models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={current_key}"
        
        try:
            response = requests.get(models_url, timeout=30)
            
            if response.status_code != 200:
                return None, f"Failed to fetch Google models ({response.status_code}): {response.text[:200]}"
            
            data = response.json()
            
            # Google format: {"models": [...]}
            if "models" in data and isinstance(data["models"], list):
                models = []
                for model in data["models"]:
                    model_name = model.get("name", "")
                    # Extract model ID from "models/gemini-2.0-flash" format
                    model_id = model_name.replace("models/", "") if model_name.startswith("models/") else model_name
                    display_name = model.get("displayName", model_id)
                    
                    # Filter to only include generateContent-capable models
                    supported_methods = model.get("supportedGenerationMethods", [])
                    if "generateContent" in supported_methods:
                        models.append({
                            "id": model_id,
                            "name": display_name
                        })
                return models, None
            
            return None, "Unknown Google models response format"
            
        except requests.exceptions.RequestException as e:
            return None, f"Request failed: {e}"
        except Exception as e:
            return None, f"Error fetching Google models: {e}"
    
    elif provider == "openrouter":
        # Fetch from OpenRouter API
        key_manager = key_managers.get("openrouter")
        if not key_manager or not key_manager.has_keys():
            return None, "No API keys configured for OpenRouter provider"
        
        current_key = key_manager.get_current_key()
        if not current_key:
            return None, "No API key available"
        
        models_url = "https://openrouter.ai/api/v1/models"
        headers = {
            "Authorization": f"Bearer {current_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.get(models_url, headers=headers, timeout=30)
            
            if response.status_code != 200:
                return None, f"Failed to fetch OpenRouter models ({response.status_code}): {response.text[:200]}"
            
            data = response.json()
            return _parse_models_response(data)
            
        except requests.exceptions.RequestException as e:
            return None, f"Request failed: {e}"
        except Exception as e:
            return None, f"Error fetching OpenRouter models: {e}"
    
    return [], None


def _parse_models_response(data):
    """Parse models response in OpenAI format"""
    # OpenAI format: {"data": [...]}
    if "data" in data and isinstance(data["data"], list):
        models = []
        for model in data["data"]:
            model_id = model.get("id", str(model))
            models.append({
                "id": model_id,
                "name": model_id,
                "owned_by": model.get("owned_by", "unknown")
            })
        return models, None
    
    # Some APIs return array directly
    if isinstance(data, list):
        models = []
        for model in data:
            if isinstance(model, str):
                models.append({"id": model, "name": model})
            else:
                model_id = model.get("id", str(model))
                models.append({"id": model_id, "name": model_id})
        return models, None
    
    return None, "Unknown models response format"


