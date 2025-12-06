#!/usr/bin/env python3
"""
Main TextEditTool application controller
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Dict

from .hotkey import HotkeyListener
from .text_handler import TextHandler
from .popups import InputPopup, PromptSelectionPopup
from .options import DEFAULT_OPTIONS, CHAT_SYSTEM_INSTRUCTION, FOLLOWUP_SYSTEM_INSTRUCTION

# Import API client directly (no wrapper needed)
from ..api_client import call_api_with_retry


class TextEditToolApp:
    """
    Main TextEditTool application controller.
    Coordinates hotkey listening, text handling, UI, and AI requests.
    """
    
    def __init__(
        self,
        config: Dict,
        ai_params: Dict,
        key_managers: Dict,
        options_file: str = "text_edit_tool_options.json"
    ):
        """
        Initialize the TextEditTool application.
        
        Args:
            config: Main configuration dictionary
            ai_params: AI parameters dictionary
            key_managers: Dictionary of KeyManager instances
            options_file: Path to the options JSON file
        """
        self.config = config
        self.ai_params = ai_params
        self.key_managers = key_managers
        self.options_file = options_file
        
        # Load options
        self.options = self._load_options()
        
        # Get TextEditTool-specific config
        self.enabled = config.get("text_edit_tool_enabled", True)
        self.hotkey = config.get("text_edit_tool_hotkey", "ctrl+space")
        
        # Initialize components
        self.hotkey_listener: Optional[HotkeyListener] = None
        self.text_handler = TextHandler()
        
        # Current state
        self.popup = None
        self.chat_window = None
        self.current_selected_text = ""
        self.is_processing = False
        self.cancel_requested = False
        
        logging.debug('TextEditToolApp initialized')
    
    def _load_options(self) -> Dict:
        """Load options from JSON file or use defaults."""
        options_path = Path(self.options_file)
        
        if options_path.exists():
            try:
                with open(options_path, 'r', encoding='utf-8') as f:
                    options = json.load(f)
                    logging.debug(f'Loaded options from {options_path}')
                    return options
            except Exception as e:
                logging.error(f'Failed to load options file: {e}')
        
        # Use defaults and save them
        logging.debug('Using default options')
        self._save_options(DEFAULT_OPTIONS)
        return DEFAULT_OPTIONS.copy()
    
    def _save_options(self, options: Dict):
        """Save options to JSON file."""
        try:
            with open(self.options_file, 'w', encoding='utf-8') as f:
                json.dump(options, f, indent=2)
                logging.debug(f'Saved options to {self.options_file}')
        except Exception as e:
            logging.error(f'Failed to save options file: {e}')
    
    def start(self):
        """Start the TextEditTool application."""
        if not self.enabled:
            logging.info('TextEditTool is disabled')
            return
        
        logging.info(f'Starting TextEditTool with hotkey: {self.hotkey}')
        
        # Create and start hotkey listener
        self.hotkey_listener = HotkeyListener(
            shortcut=self.hotkey,
            callback=self._on_hotkey_pressed
        )
        self.hotkey_listener.start()
        
        print(f"  ✓ TextEditTool: Hotkey '{self.hotkey}' registered")
    
    def stop(self):
        """Stop the TextEditTool application."""
        logging.info('Stopping TextEditTool')
        
        if self.hotkey_listener:
            self.hotkey_listener.stop()
            self.hotkey_listener = None
        
        self.cancel_requested = True
    
    def pause(self):
        """Pause the hotkey listener."""
        if self.hotkey_listener:
            self.hotkey_listener.pause()
    
    def resume(self):
        """Resume the hotkey listener."""
        if self.hotkey_listener:
            self.hotkey_listener.resume()
    
    def _on_hotkey_pressed(self):
        """Handle hotkey press event."""
        logging.debug('Hotkey pressed')
        
        if self.is_processing:
            logging.debug('Already processing, ignoring hotkey')
            return
        
        self.cancel_requested = False
        
        # Show popup immediately in a new thread
        threading.Thread(target=self._show_popup, daemon=True).start()
    
    def _show_popup(self):
        """Show the appropriate popup window."""
        logging.debug('Showing popup window')
        
        # Get selected text with quick check first, then retry if empty
        self.current_selected_text = self.text_handler.get_selected_text(sleep_duration=0.15)
        
        if self.current_selected_text:
            logging.debug(f'Selected text: "{self.current_selected_text[:50]}..."')
            # Text selected - show prompt selection popup
            self.popup = PromptSelectionPopup(
                options=self.options,
                on_option_selected=self._on_option_selected,
                on_close=self._on_popup_closed
            )
            self.popup.show(self.current_selected_text)
        else:
            # No text selected - show simple input popup immediately
            logging.debug('No text selected, showing input popup')
            self.popup = InputPopup(
                on_submit=self._on_direct_chat,
                on_close=self._on_popup_closed
            )
            self.popup.show()
    
    def _on_popup_closed(self):
        """Handle popup window close."""
        logging.debug('Popup window closed')
        self.popup = None
    
    def _on_direct_chat(self, user_input: str):
        """Handle direct chat input (no selected text)."""
        logging.debug(f'Direct chat input: {user_input[:50]}...')
        
        self.is_processing = True
        
        threading.Thread(
            target=self._process_direct_chat,
            args=(user_input,),
            daemon=True
        ).start()
    
    def _on_option_selected(self, option_key: str, selected_text: str, custom_input: Optional[str], response_mode: str = "default"):
        """
        Handle option selection from popup.
        
        Args:
            option_key: The selected option key
            selected_text: The selected text
            custom_input: Custom input text (for Custom option)
            response_mode: Response mode ("default", "replace", or "show")
        """
        logging.debug(f'Option selected: {option_key}, mode: {response_mode}')
        
        self.is_processing = True
        
        threading.Thread(
            target=self._process_option,
            args=(option_key, selected_text, custom_input, response_mode),
            daemon=True
        ).start()
    
    def _call_api(self, messages, provider=None, model=None, on_chunk=None):
        """
        Call the AI API with streaming support when enabled.
        
        Args:
            messages: API messages
            provider: Optional provider override
            model: Optional model override
            on_chunk: Optional callback for each text chunk (for real-time typing)
        """
        if not provider:
            provider = self.config.get("default_provider", "google")
        
        streaming_enabled = self.config.get("streaming_enabled", True)
        
        if streaming_enabled:
            # Use streaming API
            from ..api_client import call_api_chat_stream
            from ..session_manager import ChatSession
            
            # Create a temporary session
            session = ChatSession(
                endpoint="textedit",
                provider=provider,
                model=model or self.config.get(f"{provider}_model")
            )
            # Add messages directly - we'll use the internal format
            for msg in messages:
                session.messages.append({"role": msg["role"], "content": msg["content"]})
            
            full_text = ""
            error = None
            
            def stream_callback(data_type, content):
                nonlocal full_text, error
                if data_type == "text":
                    full_text += content
                    # Call chunk callback for real-time processing
                    if on_chunk:
                        on_chunk(content)
                    else:
                        # Print streaming to console
                        print(content, end="", flush=True)
                elif data_type == "error":
                    error = content
            
            text, reasoning, usage, err = call_api_chat_stream(
                session, self.config, self.ai_params, self.key_managers, stream_callback
            )
            if not on_chunk:
                print()  # Newline after streaming
            
            if self.cancel_requested:
                return None, "Request cancelled"
            
            return text, err
        else:
            # Non-streaming fallback
            response, error = call_api_with_retry(
                provider=provider,
                messages=messages,
                model_override=model,
                config=self.config,
                ai_params=self.ai_params,
                key_managers=self.key_managers
            )
            
            if self.cancel_requested:
                return None, "Request cancelled"
            
            return response, error
    
    def _type_text(self, text: str):
        """Type text incrementally using keyboard"""
        try:
            self.text_handler.keyboard.type(text)
        except Exception as e:
            logging.error(f"Error typing text: {e}")
    
    def _process_direct_chat(self, user_input: str):
        """Process direct chat input."""
        try:
            messages = [
                {"role": "system", "content": CHAT_SYSTEM_INSTRUCTION},
                {"role": "user", "content": user_input}
            ]
            
            # Check default_show setting
            default_show = self.config.get("default_show", "no")
            show_gui = str(default_show).lower() in ("yes", "true", "1")
            
            if show_gui:
                # For GUI mode, stream to console then show window
                print(f"\n{'─'*60}")
                print(f"[AI Response]...")
                
                response, error = self._call_api(messages)
                
                if error:
                    logging.error(f'Direct chat failed: {error}')
                    print(f"  [Error] {error}")
                    self.is_processing = False
                    return
                
                if response:
                    self._show_chat_window("AI Chat", response, user_input)
                print(f"{'─'*60}\n")
            else:
                # Replace mode: type response in real-time
                print(f"[AI Response] Typing to active field...")
                
                def type_chunk(chunk):
                    """Type each chunk as it arrives"""
                    self._type_text(chunk)
                
                response, error = self._call_api(messages, on_chunk=type_chunk)
                
                if error:
                    logging.error(f'Direct chat failed: {error}')
                    print(f"  [Error] {error}")
                    self.is_processing = False
                    return
                
                print(f"\n✓ Response typed ({len(response) if response else 0} chars)")
            
        except Exception as e:
            logging.error(f'Error in direct chat: {e}')
        finally:
            self.is_processing = False
    
    def _process_option(self, option_key: str, selected_text: str, custom_input: Optional[str], response_mode: str = "default"):
        """
        Process the selected option.
        
        Args:
            option_key: The selected option key
            selected_text: The selected text
            custom_input: Custom input text
            response_mode: Response mode ("default", "replace", or "show")
        """
        try:
            option = self.options.get(option_key, {})
            
            # Determine if this should open in a window based on response mode
            if response_mode == "show":
                open_in_window = True
            elif response_mode == "replace":
                open_in_window = False
            else:  # "default" - use the prompt's setting
                open_in_window = option.get("open_in_window", False)
            
            # Build prompt
            prefix = option.get("prefix", "")
            system_instruction = option.get("instruction", "")
            
            if option_key == "Custom" and custom_input:
                prompt = f"{prefix}Described change: {custom_input}\n\nText: {selected_text}"
            else:
                prompt = f"{prefix}{selected_text}"
            
            logging.debug(f'Getting AI response for {option_key}')
            
            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ]
            
            response, error = self._call_api(messages)
            
            if error:
                logging.error(f'Option processing failed: {error}')
                self.is_processing = False
                return
            
            if not response:
                logging.error('No response from AI')
                self.is_processing = False
                return
            
            # Handle response
            if open_in_window:
                self._show_chat_window(f"{option_key} Result", response, selected_text)
            else:
                self._replace_text(response)
            
        except Exception as e:
            logging.error(f'Error processing option: {e}')
        finally:
            self.is_processing = False
    
    def _replace_text(self, new_text: str):
        """Replace the selected text with new text."""
        success = self.text_handler.replace_selected_text(new_text)
        if success:
            logging.debug('Text replaced successfully')
        else:
            logging.error('Failed to replace text')
    
    def _show_chat_window(self, title: str, response: str, original_text: str):
        """Show the response in a chat window."""
        logging.debug('Showing chat window')
        
        # Import here to avoid circular dependency
        from .core import show_chat_gui
        from ..session_manager import ChatSession
        
        # Create a temporary session for this response
        session = ChatSession(
            endpoint="textedit",
            provider=self.config.get("default_provider", "google"),
            model=self.config.get("google_model") if self.config.get("default_provider") == "google" else None
        )
        session.title = title
        
        # Add the original context if any
        if original_text:
            session.add_message("user", original_text)
        
        session.add_message("assistant", response)
        
        # Show the chat window
        show_chat_gui(session, initial_response=response)
    
    def is_running(self) -> bool:
        """Check if TextEditTool is running."""
        return self.hotkey_listener is not None and self.hotkey_listener.is_running()
    
    def is_paused(self) -> bool:
        """Check if TextEditTool is paused."""
        return self.hotkey_listener is not None and self.hotkey_listener.is_paused()
    
    def get_status(self) -> Dict:
        """Get current status."""
        return {
            "enabled": self.enabled,
            "running": self.is_running(),
            "paused": self.is_paused(),
            "hotkey": self.hotkey,
            "processing": self.is_processing
        }
