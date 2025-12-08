"""
OpenAI-Compatible Provider

Supports:
- Custom OpenAI-compatible APIs
- OpenRouter
- Google's OpenAI-compatible endpoint (with extra_body.google for safety/thinking)

Reference: JSON-request-reference.md and reverse-proxy/src/upstream/openai-compatible.js
"""

import json
import time
from typing import List, Dict, Optional, Any
import requests

from .base import (
    BaseProvider, 
    ProviderResult, 
    StreamCallback,
    UsageData,
    CallbackType,
    RetryReason,
    estimate_tokens,
    estimate_message_tokens
)


# Safety settings for Google's OpenAI-compatible endpoint
# Per JSON-request-reference.md - must use BLOCK_NONE (not OFF)
GOOGLE_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
]


class OpenAICompatibleProvider(BaseProvider):
    """
    Provider for OpenAI-compatible APIs.
    
    Handles:
    - Custom endpoints (any OpenAI-compatible API)
    - OpenRouter (openrouter.ai)
    - Google's OpenAI-compatible endpoint (generativelanguage.googleapis.com/v1beta/openai)
    
    Features:
    - Streaming with retry logic
    - Empty response detection and retry
    - Thinking/reasoning support via reasoning_effort and extra_body.google
    - Key rotation on errors
    """
    
    # Known endpoint types
    ENDPOINT_CUSTOM = "custom"
    ENDPOINT_OPENROUTER = "openrouter"
    ENDPOINT_GOOGLE = "google"
    
    def __init__(
        self,
        endpoint_type: str,
        base_url: str,
        key_manager=None,
        config: Optional[Dict] = None
    ):
        """
        Initialize the OpenAI-compatible provider.
        
        Args:
            endpoint_type: Type of endpoint (custom, openrouter, google)
            base_url: Base URL for the API (will be normalized)
            key_manager: Key manager for API key rotation
            config: Configuration dict with thinking settings etc.
        """
        super().__init__(f"OpenAI-Compat/{endpoint_type}", key_manager)
        self.endpoint_type = endpoint_type
        self.base_url = self._normalize_url(base_url)
        self.config = config or {}
    
    def _normalize_url(self, url: str) -> str:
        """Normalize the base URL - strip trailing slash and /chat/completions"""
        if not url:
            return ""
        url = url.strip().rstrip("/")
        if url.endswith("/chat/completions"):
            url = url[:-17]
        return url
    
    def _get_completions_url(self) -> str:
        """Get the full chat completions URL"""
        return f"{self.base_url}/chat/completions"
    
    def _get_models_url(self) -> str:
        """Get the models endpoint URL"""
        return f"{self.base_url}/models"
    
    def _is_google_endpoint(self) -> bool:
        """
        Check if this is a Google endpoint (needs extra_body).
        
        Detects Google endpoints by:
        - Explicit endpoint_type == ENDPOINT_GOOGLE
        - URL containing "googleapis.com"
        - URL containing "google" keyword (flexible detection)
        """
        if self.endpoint_type == self.ENDPOINT_GOOGLE:
            return True
        
        url_lower = self.base_url.lower()
        return "googleapis.com" in url_lower or "google" in url_lower
    
    def _get_headers(self, api_key: str) -> Dict[str, str]:
        """Get request headers"""
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def _build_request_body(
        self,
        messages: List[Dict],
        model: str,
        params: Dict,
        thinking_enabled: bool,
        streaming: bool
    ) -> Dict:
        """
        Build the request body with proper thinking/safety configuration.
        
        Per JSON-request-reference.md:
        - stream: true + stream_options: { include_usage: true } for streaming
        - reasoning_effort: "high"/"medium"/"low" for thinking
        - extra_body.google.thinking_config.include_thoughts: true for Google
        - extra_body.google.safety_settings with BLOCK_NONE for Google
        """
        body = {
            "model": model,
            "messages": messages
        }
        
        # Streaming configuration
        if streaming:
            body["stream"] = True
            body["stream_options"] = {"include_usage": True}
        
        # Copy generation parameters
        for key, value in params.items():
            if key not in ("stream", "stream_options") and value is not None:
                body[key] = value
        
        # Thinking/reasoning configuration
        if thinking_enabled:
            reasoning_effort = self.config.get("reasoning_effort", "high")
            body["reasoning_effort"] = reasoning_effort
            
            # For Google endpoint, add extra_body with thinking_config and safety
            if self._is_google_endpoint():
                body["extra_body"] = {
                    "google": {
                        "thinking_config": {
                            "include_thoughts": True
                        },
                        "safety_settings": GOOGLE_SAFETY_SETTINGS
                    }
                }
        elif self._is_google_endpoint():
            # Still add safety settings even without thinking
            body["extra_body"] = {
                "google": {
                    "safety_settings": GOOGLE_SAFETY_SETTINGS
                }
            }
        
        return body
    
    def generate_stream(
        self,
        messages: List[Dict],
        model: str,
        params: Dict,
        callback: StreamCallback,
        thinking_enabled: bool = False,
        retry_count: int = 0
    ) -> ProviderResult:
        """
        Generate a streaming response with full retry logic.
        
        Retry behavior (matching reverse-proxy):
        - 429: Immediate key rotation, retry
        - 401/402/403: Immediate key rotation, retry
        - 5xx: 2 second delay, retry
        - Empty response: Key rotation, 2 second delay, retry
        - Network error: Key rotation, 1 second delay, retry
        """
        if not self.key_manager or not self.key_manager.has_keys():
            return ProviderResult(
                success=False,
                error=f"No API keys configured for {self.name}"
            )
        
        current_key = self.key_manager.get_current_key()
        if not current_key:
            return ProviderResult(
                success=False,
                error="No API key available"
            )
        
        key_num = self.key_manager.get_key_number()
        timeout = self.config.get("request_timeout", 120)
        
        url = self._get_completions_url()
        headers = self._get_headers(current_key)
        body = self._build_request_body(messages, model, params, thinking_enabled, streaming=True)
        
        self.log_request(model, key_num, thinking_enabled, streaming=True, retry=retry_count)
        
        # Accumulators for content
        accumulated_content = ""
        accumulated_thinking = ""
        accumulated_tool_calls = []
        usage_data = None
        
        try:
            # Make streaming request
            response = requests.post(
                url,
                headers=headers,
                json=body,
                timeout=timeout,
                stream=True
            )
            
            # Handle error responses
            if response.status_code != 200:
                error_text = response.text[:500]
                status_code = response.status_code
                
                reason = self.get_retry_reason(status_code, error_text)
                
                if self.should_retry(reason, retry_count):
                    delay = self.get_retry_delay(reason)
                    self.log_retry(reason, retry_count + 1, delay)
                    
                    # Rotate key for rate limit and auth errors
                    if reason in (RetryReason.RATE_LIMITED, RetryReason.AUTH_ERROR):
                        self.rotate_key_if_possible(f"({reason.value})")
                    
                    if delay > 0:
                        time.sleep(delay)
                    
                    return self.generate_stream(
                        messages, model, params, callback, thinking_enabled, retry_count + 1
                    )
                
                self.log_error(f"API error: {error_text}", status_code)
                callback(CallbackType.ERROR, error_text)
                return ProviderResult(
                    success=False,
                    error=f"API error ({status_code}): {error_text}",
                    retry_count=retry_count
                )
            
            # Process streaming response
            response.encoding = 'utf-8'
            
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                
                line = line.strip()
                
                if line == "data: [DONE]":
                    callback(CallbackType.DONE, None)
                    break
                
                if not line.startswith("data: "):
                    continue
                
                try:
                    data = json.loads(line[6:])
                    choice = data.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    
                    # Handle regular content
                    content = delta.get("content", "")
                    if content:
                        accumulated_content += content
                        callback(CallbackType.TEXT, content)
                    
                    # Handle reasoning_content (DeepSeek/thinking style)
                    reasoning = delta.get("reasoning_content", "")
                    if reasoning:
                        accumulated_thinking += reasoning
                        callback(CallbackType.THINKING, reasoning)
                    
                    # Handle tool calls
                    tool_calls = delta.get("tool_calls")
                    if tool_calls:
                        accumulated_tool_calls.extend(tool_calls)
                        callback(CallbackType.TOOL_CALLS, tool_calls)
                    
                    # Handle usage data (comes with stream_options.include_usage)
                    if "usage" in data:
                        usage = data["usage"]
                        usage_data = UsageData(
                            prompt_tokens=usage.get("prompt_tokens", 0),
                            completion_tokens=usage.get("completion_tokens", 0),
                            total_tokens=usage.get("total_tokens", 0)
                        )
                        callback(CallbackType.USAGE, usage_data.to_dict())
                
                except json.JSONDecodeError:
                    continue
            
            # Check for empty response
            output_tokens = usage_data.completion_tokens if usage_data else 0
            
            if self.detect_empty_response(
                accumulated_content,
                accumulated_thinking,
                accumulated_tool_calls,
                output_tokens
            ):
                self.log("warn", "Empty response detected (no content, 0 output tokens)")
                
                if self.should_retry(RetryReason.EMPTY_RESPONSE, retry_count):
                    delay = self.get_retry_delay(RetryReason.EMPTY_RESPONSE)
                    self.log_retry(RetryReason.EMPTY_RESPONSE, retry_count + 1, delay)
                    self.rotate_key_if_possible("(empty response)")
                    
                    if delay > 0:
                        time.sleep(delay)
                    
                    return self.generate_stream(
                        messages, model, params, callback, thinking_enabled, retry_count + 1
                    )
                
                return ProviderResult(
                    success=False,
                    error="Empty response after retries exhausted",
                    retry_count=retry_count
                )
            
            # Estimate usage if not provided
            if not usage_data:
                input_tokens = estimate_message_tokens(messages)
                output_tokens = estimate_tokens(accumulated_content + accumulated_thinking)
                usage_data = UsageData(
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    estimated=True
                )
                callback(CallbackType.USAGE, usage_data.to_dict())
            
            self.log_success(key_num)
            
            return ProviderResult(
                success=True,
                content=accumulated_content,
                thinking_content=accumulated_thinking,
                tool_calls=accumulated_tool_calls,
                usage=usage_data,
                retry_count=retry_count
            )
        
        except requests.exceptions.Timeout:
            self.log_error(f"Request timeout after {timeout}s")
            
            if self.should_retry(RetryReason.NETWORK_ERROR, retry_count):
                delay = self.get_retry_delay(RetryReason.NETWORK_ERROR)
                self.log_retry(RetryReason.NETWORK_ERROR, retry_count + 1, delay)
                self.rotate_key_if_possible("(timeout)")
                
                if delay > 0:
                    time.sleep(delay)
                
                return self.generate_stream(
                    messages, model, params, callback, thinking_enabled, retry_count + 1
                )
            
            callback(CallbackType.ERROR, f"Request timeout after {timeout}s")
            return ProviderResult(
                success=False,
                error=f"Request timeout after {timeout}s",
                retry_count=retry_count
            )
        
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.log_error(f"Network error: {error_msg}")
            
            if self.should_retry(RetryReason.NETWORK_ERROR, retry_count):
                delay = self.get_retry_delay(RetryReason.NETWORK_ERROR)
                self.log_retry(RetryReason.NETWORK_ERROR, retry_count + 1, delay)
                self.rotate_key_if_possible("(network error)")
                
                if delay > 0:
                    time.sleep(delay)
                
                return self.generate_stream(
                    messages, model, params, callback, thinking_enabled, retry_count + 1
                )
            
            callback(CallbackType.ERROR, error_msg)
            return ProviderResult(
                success=False,
                error=f"Network error: {error_msg}",
                retry_count=retry_count
            )
        
        except Exception as e:
            error_msg = str(e)
            self.log_error(f"Unexpected error: {error_msg}")
            
            if self.should_retry(RetryReason.SERVER_ERROR, retry_count):
                delay = self.get_retry_delay(RetryReason.SERVER_ERROR)
                self.log_retry(RetryReason.SERVER_ERROR, retry_count + 1, delay)
                
                if delay > 0:
                    time.sleep(delay)
                
                return self.generate_stream(
                    messages, model, params, callback, thinking_enabled, retry_count + 1
                )
            
            callback(CallbackType.ERROR, error_msg)
            return ProviderResult(
                success=False,
                error=f"Unexpected error: {error_msg}",
                retry_count=retry_count
            )
    
    def generate(
        self,
        messages: List[Dict],
        model: str,
        params: Dict,
        thinking_enabled: bool = False,
        retry_count: int = 0
    ) -> ProviderResult:
        """
        Generate a non-streaming response with retry logic.
        """
        if not self.key_manager or not self.key_manager.has_keys():
            return ProviderResult(
                success=False,
                error=f"No API keys configured for {self.name}"
            )
        
        current_key = self.key_manager.get_current_key()
        if not current_key:
            return ProviderResult(
                success=False,
                error="No API key available"
            )
        
        key_num = self.key_manager.get_key_number()
        timeout = self.config.get("request_timeout", 120)
        
        url = self._get_completions_url()
        headers = self._get_headers(current_key)
        body = self._build_request_body(messages, model, params, thinking_enabled, streaming=False)
        
        self.log_request(model, key_num, thinking_enabled, streaming=False, retry=retry_count)
        
        try:
            response = requests.post(url, headers=headers, json=body, timeout=timeout)
            
            # Handle error responses
            if response.status_code != 200:
                error_text = response.text[:500]
                status_code = response.status_code
                
                reason = self.get_retry_reason(status_code, error_text)
                
                if self.should_retry(reason, retry_count):
                    delay = self.get_retry_delay(reason)
                    self.log_retry(reason, retry_count + 1, delay)
                    
                    if reason in (RetryReason.RATE_LIMITED, RetryReason.AUTH_ERROR):
                        self.rotate_key_if_possible(f"({reason.value})")
                    
                    if delay > 0:
                        time.sleep(delay)
                    
                    return self.generate(messages, model, params, thinking_enabled, retry_count + 1)
                
                self.log_error(f"API error: {error_text}", status_code)
                return ProviderResult(
                    success=False,
                    error=f"API error ({status_code}): {error_text}",
                    retry_count=retry_count
                )
            
            # Parse response
            data = response.json()
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            
            content = message.get("content", "")
            reasoning = message.get("reasoning_content", "")
            tool_calls = message.get("tool_calls", [])
            
            # Parse usage
            usage = data.get("usage", {})
            usage_data = UsageData(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0)
            )
            
            # Check for empty response
            if self.detect_empty_response(content, reasoning, tool_calls, usage_data.completion_tokens):
                self.log("warn", "Empty response detected")
                
                if self.should_retry(RetryReason.EMPTY_RESPONSE, retry_count):
                    delay = self.get_retry_delay(RetryReason.EMPTY_RESPONSE)
                    self.log_retry(RetryReason.EMPTY_RESPONSE, retry_count + 1, delay)
                    self.rotate_key_if_possible("(empty response)")
                    
                    if delay > 0:
                        time.sleep(delay)
                    
                    return self.generate(messages, model, params, thinking_enabled, retry_count + 1)
                
                return ProviderResult(
                    success=False,
                    error="Empty response after retries exhausted",
                    retry_count=retry_count
                )
            
            self.log_success(key_num)
            
            return ProviderResult(
                success=True,
                content=content,
                thinking_content=reasoning,
                tool_calls=tool_calls,
                usage=usage_data,
                retry_count=retry_count
            )
        
        except requests.exceptions.Timeout:
            self.log_error(f"Request timeout after {timeout}s")
            
            if self.should_retry(RetryReason.NETWORK_ERROR, retry_count):
                delay = self.get_retry_delay(RetryReason.NETWORK_ERROR)
                self.log_retry(RetryReason.NETWORK_ERROR, retry_count + 1, delay)
                self.rotate_key_if_possible("(timeout)")
                
                if delay > 0:
                    time.sleep(delay)
                
                return self.generate(messages, model, params, thinking_enabled, retry_count + 1)
            
            return ProviderResult(
                success=False,
                error=f"Request timeout after {timeout}s",
                retry_count=retry_count
            )
        
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.log_error(f"Network error: {error_msg}")
            
            if self.should_retry(RetryReason.NETWORK_ERROR, retry_count):
                delay = self.get_retry_delay(RetryReason.NETWORK_ERROR)
                self.log_retry(RetryReason.NETWORK_ERROR, retry_count + 1, delay)
                self.rotate_key_if_possible("(network error)")
                
                if delay > 0:
                    time.sleep(delay)
                
                return self.generate(messages, model, params, thinking_enabled, retry_count + 1)
            
            return ProviderResult(
                success=False,
                error=f"Network error: {error_msg}",
                retry_count=retry_count
            )
        
        except Exception as e:
            error_msg = str(e)
            self.log_error(f"Unexpected error: {error_msg}")
            
            return ProviderResult(
                success=False,
                error=f"Unexpected error: {error_msg}",
                retry_count=retry_count
            )
    
    def fetch_models(self) -> tuple[List[Dict], Optional[str]]:
        """Fetch available models from the API"""
        if not self.key_manager or not self.key_manager.has_keys():
            return None, f"No API keys configured for {self.name}"
        
        current_key = self.key_manager.get_current_key()
        if not current_key:
            return None, "No API key available"
        
        url = self._get_models_url()
        headers = self._get_headers(current_key)
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code != 200:
                return None, f"Failed to fetch models ({response.status_code}): {response.text[:200]}"
            
            data = response.json()
            
            # OpenAI format: { "data": [...] }
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
        
        except requests.exceptions.RequestException as e:
            return None, f"Request failed: {e}"
        except Exception as e:
            return None, f"Error fetching models: {e}"