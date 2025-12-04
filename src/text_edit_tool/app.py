#!/usr/bin/env python3
"""
Main TextEditTool application controller
"""

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Callable

from .hotkey_listener import HotkeyListener
from .text_handler import TextHandler
from .popup_window import PopupWindow
from .response_window import ResponseWindow
from .ai_client import TextEditToolAIClient
from .options import DEFAULT_OPTIONS, CHAT_SYSTEM_INSTRUCTION, FOLLOWUP_SYSTEM_INSTRUCTION, ERROR_INCOMPATIBLE


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
        self.response_mode = config.get("text_edit_tool_response_mode", "replace")
        
        # Initialize components
        self.hotkey_listener: Optional[HotkeyListener] = None
        self.text_handler = TextHandler()
        self.ai_client = TextEditToolAIClient(config, ai_params, key_managers)
        
        # Current state
        self.popup_window: Optional[PopupWindow] = None
        self.response_window: Optional[ResponseWindow] = None
        self.current_selected_text = ""
        self.is_processing = False
        
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
        print(f"  ✓ TextEditTool: Response mode = {self.response_mode}")
    
    def stop(self):
        """Stop the TextEditTool application."""
        logging.info('Stopping TextEditTool')
        
        if self.hotkey_listener:
            self.hotkey_listener.stop()
            self.hotkey_listener = None
        
        # Cancel any pending AI request
        if self.ai_client:
            self.ai_client.cancel()
    
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
        
        # Cancel any previous AI request
        self.ai_client.cancel()
        
        # Get selected text
        self.current_selected_text = self.text_handler.get_selected_text_with_retry()
        logging.debug(f'Selected text: "{self.current_selected_text[:50]}..."' if self.current_selected_text else 'No text selected')
        
        # Show popup in main thread
        threading.Thread(target=self._show_popup, daemon=True).start()
    
    def _show_popup(self):
        """Show the popup window."""
        logging.debug('Showing popup window')
        
        self.popup_window = PopupWindow(
            options=self.options,
            on_option_selected=self._on_option_selected,
            on_close=self._on_popup_closed
        )
        
        self.popup_window.show(self.current_selected_text)
    
    def _on_popup_closed(self):
        """Handle popup window close."""
        logging.debug('Popup window closed')
        self.popup_window = None
    
    def _on_option_selected(self, option_key: str, selected_text: str, custom_input: Optional[str]):
        """
        Handle option selection from popup.
        
        Args:
            option_key: The selected option key
            selected_text: The selected text
            custom_input: Custom input text (for Custom option)
        """
        logging.debug(f'Option selected: {option_key}')
        
        self.is_processing = True
        
        # Process in background thread
        threading.Thread(
            target=self._process_option,
            args=(option_key, selected_text, custom_input),
            daemon=True
        ).start()
    
    def _process_option(self, option_key: str, selected_text: str, custom_input: Optional[str]):
        """
        Process the selected option.
        
        Args:
            option_key: The selected option key
            selected_text: The selected text
            custom_input: Custom input text
        """
        try:
            option = self.options.get(option_key, {})
            
            # Determine if this should open in a window
            open_in_window = option.get("open_in_window", False)
            
            # For Custom with no text, always open in window (chat mode)
            if option_key == "Custom" and not selected_text.strip():
                open_in_window = True
            
            # Override with config setting if set to popup
            if self.response_mode == "popup":
                open_in_window = True
            
            # Build prompt
            if option_key == "Custom" and not selected_text.strip():
                # Direct chat mode
                prompt = custom_input
                system_instruction = CHAT_SYSTEM_INSTRUCTION
            else:
                prefix = option.get("prefix", "")
                system_instruction = option.get("instruction", "")
                
                if option_key == "Custom" and custom_input:
                    prompt = f"{prefix}Described change: {custom_input}\n\nText: {selected_text}"
                else:
                    prompt = f"{prefix}{selected_text}"
            
            logging.debug(f'Getting AI response for {option_key}')
            
            # Get AI response
            response = self.ai_client.get_response(
                system_instruction=system_instruction,
                prompt=prompt
            )
            
            if not response:
                logging.error('No response from AI')
                self.is_processing = False
                return
            
            # Check for error response
            if response.strip() == ERROR_INCOMPATIBLE:
                logging.warning('Text incompatible with request')
                # Could show a notification here
                self.is_processing = False
                return
            
            # Handle response
            if open_in_window:
                self._show_response_window(option_key, response, selected_text)
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
    
    def _show_response_window(self, title: str, response: str, selected_text: str):
        """
        Show the response window.
        
        Args:
            title: Window title
            response: AI response
            selected_text: Original selected text
        """
        logging.debug('Showing response window')
        
        self.response_window = ResponseWindow(
            title=f"{title} Result",
            on_followup=self._on_followup_question,
            on_close=self._on_response_window_closed
        )
        
        self.response_window.show(
            initial_response=response,
            selected_text=selected_text
        )
    
    def _on_response_window_closed(self):
        """Handle response window close."""
        logging.debug('Response window closed')
        self.response_window = None
    
    def _on_followup_question(self, question: str, chat_history: list):
        """
        Handle follow-up question from response window.
        
        Args:
            question: The follow-up question
            chat_history: Current chat history
        """
        logging.debug(f'Follow-up question: {question}')
        
        def callback(response, error):
            if not self.response_window:
                return
            
            if error:
                self.response_window.show_error(error)
            elif response:
                self.response_window.add_response(response)
        
        # Get response with chat history
        self.ai_client.get_chat_response_async(
            system_instruction=FOLLOWUP_SYSTEM_INSTRUCTION,
            messages=chat_history,
            callback=callback
        )
    
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
            "response_mode": self.response_mode,
            "processing": self.is_processing
        }
