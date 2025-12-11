#!/usr/bin/env python3
"""
Main TextEditTool application controller

Settings Override Hierarchy (for display mode):
1. Radio button in popup (if not "Default") - highest priority
2. show_chat_window_instead_of_replace per-action option - per-action default
3. show_ai_response_in_chat_window in config - global default (InputPopup only)

For API endpoints, the ?show= URL parameter takes highest priority.
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
from .options import DEFAULT_OPTIONS, SETTINGS_KEY, DEFAULT_SETTINGS

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
        default_with_settings = {SETTINGS_KEY: DEFAULT_SETTINGS.copy(), **DEFAULT_OPTIONS}
        self._save_options(default_with_settings)
        return default_with_settings
    
    def _get_setting(self, key: str, default=None):
        """Get a setting from the _settings section of options."""
        settings = self.options.get(SETTINGS_KEY, {})
        return settings.get(key, DEFAULT_SETTINGS.get(key, default))
    
    def _get_action_options(self) -> Dict:
        """Get action options (excluding _settings)."""
        return {k: v for k, v in self.options.items() if k != SETTINGS_KEY}
    
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
        """Show the appropriate popup window via GUICoordinator."""
        logging.debug('Showing popup window via GUICoordinator')
        
        from .core import GUICoordinator
        
        # Get selected text with quick check first, then retry if empty
        self.current_selected_text = self.text_handler.get_selected_text(sleep_duration=0.15)
        
        if self.current_selected_text:
            logging.debug(f'Selected text: "{self.current_selected_text[:50]}..."')
            # Text selected - show prompt selection popup via coordinator
            # Pass full options (including _settings for popup_items_per_page)
            GUICoordinator.get_instance().request_prompt_popup(
                options=self.options,
                on_option_selected=self._on_option_selected,
                on_close=self._on_popup_closed,
                selected_text=self.current_selected_text
            )
        else:
            # No text selected - show simple input popup via coordinator
            logging.debug('No text selected, showing input popup')
            GUICoordinator.get_instance().request_input_popup(
                on_submit=self._on_direct_chat,
                on_close=self._on_popup_closed
            )
    
    def _on_popup_closed(self):
        """Handle popup window close."""
        logging.debug('Popup window closed')
        self.popup = None
    
    def _on_direct_chat(self, user_input: str, response_mode: str = "default"):
        """
        Handle direct chat input (no selected text).
        
        Args:
            user_input: The user's chat input
            response_mode: Response mode ("default", "replace", or "show")
        """
        logging.debug(f'Direct chat input: {user_input[:50]}..., mode: {response_mode}')
        
        self.is_processing = True
        
        threading.Thread(
            target=self._process_direct_chat,
            args=(user_input, response_mode),
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
    
    def _call_api(self, messages, provider=None, model=None, on_chunk=None, origin_override=None):
        """
        Call the AI API with streaming support when enabled.
        
        Args:
            messages: API messages
            provider: Optional provider override
            model: Optional model override
            on_chunk: Optional callback for each text chunk (for real-time typing)
            origin_override: Optional RequestOrigin override
        """
        from ..request_pipeline import RequestPipeline, RequestContext, RequestOrigin, StreamCallback
        from ..session_manager import ChatSession
        
        if not provider:
            provider = self.config.get("default_provider", "google")
        
        streaming_enabled = self.config.get("streaming_enabled", True)
        
        # Determine origin
        origin = origin_override or RequestOrigin.POPUP_INPUT
        
        # Setup context
        ctx = RequestContext(
            origin=origin,
            provider=provider,
            model=model or self.config.get(f"{provider}_model"),
            streaming=streaming_enabled,
            thinking_enabled=self.config.get("thinking_enabled", False)
        )
        
        if streaming_enabled:
            # Create a temporary session (uses current config, not stored provider/model)
            session = ChatSession(
                endpoint="textedit"
            )
            # Add messages directly
            for msg in messages:
                session.messages.append({"role": msg["role"], "content": msg["content"]})
            
            # Setup callbacks
            def on_text(content):
                if on_chunk:
                    on_chunk(content)
                else:
                    # Print streaming to console only if no handler
                    print(content, end="", flush=True)
            
            def on_done():
                if not on_chunk:
                    print()  # Newline after streaming
            
            callbacks = StreamCallback(
                on_text=on_text,
                on_done=on_done
            )
            
            ctx = RequestPipeline.execute_streaming(
                ctx,
                session,
                self.config,
                self.ai_params,
                self.key_managers,
                callbacks
            )
            
            if self.cancel_requested:
                return None, "Request cancelled"
            
            return ctx.response_text, ctx.error
        else:
            # Non-streaming
            ctx = RequestPipeline.execute_simple(
                ctx,
                messages,
                self.config,
                self.ai_params,
                self.key_managers
            )
            
            if self.cancel_requested:
                return None, "Request cancelled"
            
            return ctx.response_text, ctx.error
    
    def _type_text_chunk(self, text: str):
        """
        Insert text chunk using keyboard typing with rate limiting.
        Avoids clipboard to prevent filling clipboard managers.
        Uses a small delay between characters for stability.
        """
        import time
        from pynput import keyboard as pykeyboard
        
        try:
            keyboard = pykeyboard.Controller()
            
            # Type each character with a small delay for stability
            for char in text:
                keyboard.type(char)
                time.sleep(0.005)  # 5ms delay per character
            
            # Small delay after chunk for application responsiveness
            time.sleep(0.01)
            
        except Exception as e:
            logging.error(f"Error typing text chunk: {e}")
    
    def _process_direct_chat(self, user_input: str, response_mode: str = "default"):
        """
        Process direct chat input.
        
        Args:
            user_input: The user's chat input
            response_mode: Response mode ("default", "replace", or "show")
                - "show": Force show in chat window
                - "replace": Force type to active field
                - "default": Use show_ai_response_in_chat_window config setting
        """
        try:
            # Get system instruction from settings
            chat_system_instruction = self._get_setting(
                "chat_system_instruction",
                "You are a helpful AI assistant."
            )
            
            messages = [
                {"role": "system", "content": chat_system_instruction},
                {"role": "user", "content": user_input}
            ]
            
            # Determine display mode based on hierarchy:
            # 1. Radio button (if not "default")
            # 2. "Custom" action setting from text_edit_tool_options.json
            # 3. Config setting show_ai_response_in_chat_window
            if response_mode == "show":
                show_gui = True
            elif response_mode == "replace":
                show_gui = False
            else:  # "default"
                # Check "Custom" option first
                action_options = self._get_action_options()
                custom_option = action_options.get("Custom", {})
                
                if "show_chat_window_instead_of_replace" in custom_option:
                    show_gui = custom_option["show_chat_window_instead_of_replace"]
                else:
                    # Fallback to global config
                    show_setting = self.config.get("show_ai_response_in_chat_window",
                                                   self.config.get("default_show", "no"))
                    show_gui = str(show_setting).lower() in ("yes", "true", "1")
            
            if show_gui:
                # For GUI mode, stream to console then show window
                print(f"\n{'─'*60}")
                print(f"[AI Response]...")
                
                from ..request_pipeline import RequestOrigin
                response, error = self._call_api(messages, origin_override=RequestOrigin.POPUP_INPUT)
                
                if error:
                    logging.error(f'Direct chat failed: {error}')
                    print(f"  [Error] {error}")
                    self.is_processing = False
                    return
                
                if response:
                    self._show_chat_window("AI Chat", response, user_input)
                print(f"{'─'*60}\n")
            else:
                # Replace mode: type response to active field
                streaming_enabled = self.config.get("streaming_enabled", True)
                
                if streaming_enabled:
                    print(f"[AI Response] Streaming to active field...")
                    
                    # Buffer to accumulate chunks before typing (helps with Unicode)
                    chunk_buffer = []
                    buffer_size = 0
                    MIN_BUFFER_CHARS = 20  # Accumulate at least 20 chars before typing
                    
                    def type_chunk(chunk):
                        """Buffer chunks and type when buffer is large enough"""
                        nonlocal chunk_buffer, buffer_size
                        chunk_buffer.append(chunk)
                        buffer_size += len(chunk)
                        
                        # Type when buffer reaches minimum size
                        if buffer_size >= MIN_BUFFER_CHARS:
                            text_to_type = ''.join(chunk_buffer)
                            chunk_buffer.clear()
                            buffer_size = 0
                            self._type_text_chunk(text_to_type)
                    
                    from ..request_pipeline import RequestOrigin
                    response, error = self._call_api(messages, on_chunk=type_chunk, origin_override=RequestOrigin.POPUP_INPUT)
                    
                    # Type any remaining buffered text
                    if chunk_buffer:
                        self._type_text_chunk(''.join(chunk_buffer))
                else:
                    print(f"[AI Response] Getting response...")
                    from ..request_pipeline import RequestOrigin
                    response, error = self._call_api(messages, origin_override=RequestOrigin.POPUP_INPUT)
                    
                    # Type the full response when non-streaming
                    if response and not error:
                        print(f"[Typing to active field...]")
                        self._type_text_chunk(response)
                
                if error:
                    logging.error(f'Direct chat failed: {error}')
                    print(f"  [Error] {error}")
                    self.is_processing = False
                    return
                
                if streaming_enabled:
                    print(f"\n✓ Response streamed ({len(response) if response else 0} chars)")
                else:
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
            custom_input: Custom input text (for Custom option)
            response_mode: Response mode ("default", "replace", or "show")
        
        Display Mode Override Hierarchy:
            1. response_mode from popup radio button (if not "default")
            2. show_chat_window_instead_of_replace per-action setting
            3. Falls back to False (replace mode)
        
        Prompt Structure:
            SYSTEM: {system_prompt}
            USER: {task}
                   {base_output_rules}
                   {text_delimiter}
                   {selected_text}
        """
        try:
            action_options = self._get_action_options()
            option = action_options.get(option_key, {})
            
            # Determine if this should open in a window based on response mode
            # Hierarchy: radio button > per-action setting > default (False)
            if response_mode == "show":
                show_in_chat_window = True
            elif response_mode == "replace":
                show_in_chat_window = False
            else:  # "default" - use the action's setting
                show_in_chat_window = option.get("show_chat_window_instead_of_replace", False)
            
            # Build prompt using new structure with backwards compatibility
            # New keys: system_prompt, task
            # Legacy keys: instruction, prefix
            system_prompt = option.get("system_prompt") or option.get("instruction", "")
            task = option.get("task") or option.get("prefix", "")
            
            # Get shared settings
            base_output_rules = self._get_setting("base_output_rules", "")
            text_delimiter = self._get_setting("text_delimiter", "\n\n")
            
            # Handle Custom action - use template for task
            if option_key == "Custom" and custom_input:
                custom_task_template = self._get_setting(
                    "custom_task_template",
                    "Apply the following change to the text below: {custom_input}"
                )
                task = custom_task_template.format(custom_input=custom_input)
            
            # Build user message: task + output rules + delimiter + text
            user_message_parts = []
            if task:
                user_message_parts.append(task)
            if base_output_rules:
                user_message_parts.append(base_output_rules)
            
            user_message = "\n\n".join(user_message_parts)
            user_message += text_delimiter + selected_text
            
            logging.debug(f'Getting AI response for {option_key}')
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
            
            from ..request_pipeline import RequestOrigin
            response, error = self._call_api(messages, origin_override=RequestOrigin.POPUP_PROMPT)
            
            if error:
                logging.error(f'Option processing failed: {error}')
                self.is_processing = False
                return
            
            if not response:
                logging.error('No response from AI')
                self.is_processing = False
                return
            
            # Handle response
            if show_in_chat_window:
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
        
        # Create a temporary session for this response (uses current config)
        session = ChatSession(
            endpoint="textedit"
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
