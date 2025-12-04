#!/usr/bin/env python3
"""
AI client adapter for TextEditTool
Bridges to the existing API client infrastructure
"""

import logging
import threading
from typing import Optional, Dict, List, Callable, Any

# Import from parent package
from ..api_client import call_api_with_retry


class TextEditToolAIClient:
    """
    AI client for TextEditTool that uses the existing API infrastructure.
    """
    
    def __init__(self, config: Dict, ai_params: Dict, key_managers: Dict):
        """
        Initialize the AI client.
        
        Args:
            config: Main configuration dictionary
            ai_params: AI parameters dictionary
            key_managers: Dictionary of KeyManager instances
        """
        self.config = config
        self.ai_params = ai_params
        self.key_managers = key_managers
        self.cancel_requested = False
        
        logging.debug('TextEditToolAIClient initialized')
    
    def get_response(
        self,
        system_instruction: str,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        callback: Optional[Callable[[str], None]] = None
    ) -> Optional[str]:
        """
        Get a response from the AI.
        
        Args:
            system_instruction: System instruction for the AI
            prompt: User prompt
            provider: Optional provider override
            model: Optional model override
            callback: Optional callback for when response is ready
            
        Returns:
            AI response text, or None if failed
        """
        self.cancel_requested = False
        
        # Use default provider if not specified
        if not provider:
            provider = self.config.get("default_provider", "google")
        
        # Build messages
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ]
        
        logging.debug(f'Getting AI response from {provider}')
        
        try:
            response, error = call_api_with_retry(
                provider=provider,
                messages=messages,
                model_override=model,
                config=self.config,
                ai_params=self.ai_params,
                key_managers=self.key_managers
            )
            
            if self.cancel_requested:
                logging.debug('Request was cancelled')
                return None
            
            if error:
                logging.error(f'AI request failed: {error}')
                return None
            
            if callback:
                callback(response)
            
            return response
            
        except Exception as e:
            logging.error(f'AI request exception: {e}')
            return None
    
    def get_response_async(
        self,
        system_instruction: str,
        prompt: str,
        callback: Callable[[Optional[str], Optional[str]], None],
        provider: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        Get a response from the AI asynchronously.
        
        Args:
            system_instruction: System instruction for the AI
            prompt: User prompt
            callback: Callback with (response, error) when done
            provider: Optional provider override
            model: Optional model override
        """
        def worker():
            try:
                response = self.get_response(
                    system_instruction=system_instruction,
                    prompt=prompt,
                    provider=provider,
                    model=model
                )
                
                if response:
                    callback(response, None)
                else:
                    callback(None, "Failed to get AI response")
                    
            except Exception as e:
                callback(None, str(e))
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread
    
    def get_chat_response(
        self,
        system_instruction: str,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        model: Optional[str] = None
    ) -> Optional[str]:
        """
        Get a chat response with message history.
        
        Args:
            system_instruction: System instruction for the AI
            messages: List of message dicts with 'role' and 'content'
            provider: Optional provider override
            model: Optional model override
            
        Returns:
            AI response text, or None if failed
        """
        self.cancel_requested = False
        
        # Use default provider if not specified
        if not provider:
            provider = self.config.get("default_provider", "google")
        
        # Build messages with system instruction first
        full_messages = [{"role": "system", "content": system_instruction}]
        full_messages.extend(messages)
        
        logging.debug(f'Getting chat response from {provider} with {len(messages)} messages')
        
        try:
            response, error = call_api_with_retry(
                provider=provider,
                messages=full_messages,
                model_override=model,
                config=self.config,
                ai_params=self.ai_params,
                key_managers=self.key_managers
            )
            
            if self.cancel_requested:
                logging.debug('Request was cancelled')
                return None
            
            if error:
                logging.error(f'Chat request failed: {error}')
                return None
            
            return response
            
        except Exception as e:
            logging.error(f'Chat request exception: {e}')
            return None
    
    def get_chat_response_async(
        self,
        system_instruction: str,
        messages: List[Dict[str, str]],
        callback: Callable[[Optional[str], Optional[str]], None],
        provider: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        Get a chat response asynchronously.
        
        Args:
            system_instruction: System instruction for the AI
            messages: List of message dicts
            callback: Callback with (response, error) when done
            provider: Optional provider override
            model: Optional model override
        """
        def worker():
            try:
                response = self.get_chat_response(
                    system_instruction=system_instruction,
                    messages=messages,
                    provider=provider,
                    model=model
                )
                
                if response:
                    callback(response, None)
                else:
                    callback(None, "Failed to get chat response")
                    
            except Exception as e:
                callback(None, str(e))
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread
    
    def cancel(self):
        """Cancel any ongoing request."""
        self.cancel_requested = True
        logging.debug('AI request cancellation requested')
