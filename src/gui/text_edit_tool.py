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
        self.abort_hotkey = config.get("text_edit_tool_abort_hotkey", "escape")
        
        # Typing speed settings
        self.typing_delay_ms = config.get("streaming_typing_delay", 5)
        self.typing_uncapped = config.get("streaming_typing_uncapped", False)
        
        # Initialize components
        self.hotkey_listener: Optional[HotkeyListener] = None
        self.text_handler = TextHandler()
        
        # Current state
        self.popup = None
        self.chat_window = None
        self.current_selected_text = ""
        self.is_processing = False
        self.cancel_requested = False
        
        # Streaming abort state
        self.streaming_aborted = False
        self._abort_listener = None
        
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
        
        print(f"  ✅ TextEditTool: Hotkey '{self.hotkey}' registered")
    
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
    
    def _start_abort_listener(self):
        """
        Start listening for abort hotkey (e.g., Escape).
        When pressed, sets streaming_aborted flag.
        """
        from pynput import keyboard as pykeyboard
        
        self.streaming_aborted = False
        
        # Parse abort hotkey to pynput key
        abort_key = self._parse_hotkey(self.abort_hotkey)
        
        def on_press(key):
            if self._key_matches(key, abort_key):
                self.streaming_aborted = True
                logging.debug("Abort hotkey pressed - stopping stream")
                return False  # Stop listener
        
        self._abort_listener = pykeyboard.Listener(on_press=on_press)
        self._abort_listener.start()
    
    def _stop_abort_listener(self):
        """Stop the abort hotkey listener."""
        if self._abort_listener:
            try:
                self._abort_listener.stop()
            except Exception:
                pass
            self._abort_listener = None
    
    def _parse_hotkey(self, hotkey_str: str):
        """Parse hotkey string to pynput key."""
        from pynput import keyboard as pykeyboard
        
        key_map = {
            "escape": pykeyboard.Key.esc,
            "esc": pykeyboard.Key.esc,
            "f1": pykeyboard.Key.f1,
            "f2": pykeyboard.Key.f2,
            "f3": pykeyboard.Key.f3,
            "f4": pykeyboard.Key.f4,
            "f5": pykeyboard.Key.f5,
            "f6": pykeyboard.Key.f6,
            "f7": pykeyboard.Key.f7,
            "f8": pykeyboard.Key.f8,
            "f9": pykeyboard.Key.f9,
            "f10": pykeyboard.Key.f10,
            "f11": pykeyboard.Key.f11,
            "f12": pykeyboard.Key.f12,
            "pause": pykeyboard.Key.pause,
            "break": pykeyboard.Key.pause,
            "scroll_lock": pykeyboard.Key.scroll_lock,
        }
        
        key_lower = hotkey_str.lower().strip()
        return key_map.get(key_lower, pykeyboard.Key.esc)
    
    def _key_matches(self, pressed_key, target_key):
        """Check if pressed key matches target."""
        try:
            return pressed_key == target_key
        except Exception:
            return False
    
    def _type_text_chunk(self, text: str) -> bool:
        """
        Insert text chunk using keyboard typing with rate limiting.
        Used for STREAMING mode only - types character by character.
        Avoids clipboard to prevent filling clipboard managers.
        Uses configurable delay between characters for stability.
        
        Args:
            text: Text to type
            
        Returns:
            True if successful, False if aborted
        """
        import time
        from pynput import keyboard as pykeyboard
        
        try:
            keyboard = pykeyboard.Controller()
            
            # Determine delay per character
            if self.typing_uncapped:
                # WARNING: Uncapped mode - no delay
                # May cause issues with some applications
                char_delay = 0
            else:
                # Configurable delay (default 5ms)
                char_delay = self.typing_delay_ms / 1000.0
            
            # Type each character with configured delay
            for char in text:
                # Check abort flag
                if self.streaming_aborted:
                    logging.debug("Typing aborted by user")
                    return False
                
                keyboard.type(char)
                if char_delay > 0:
                    time.sleep(char_delay)
            
            # Small delay after chunk for application responsiveness
            if not self.typing_uncapped:
                time.sleep(0.01)
            
            return True
            
        except Exception as e:
            logging.error(f"Error typing text chunk: {e}")
            return False
    
    def _paste_text_instant(self, text: str) -> bool:
        """
        Paste text instantly using clipboard.
        Used for NON-STREAMING mode - pastes all text at once.
        
        This is faster than character-by-character typing and provides
        a better user experience when streaming is disabled.
        
        Args:
            text: The text to paste
            
        Returns:
            True if successful, False otherwise
        """
        import time
        import pyperclip
        from pynput import keyboard as pykeyboard
        
        if not text:
            return False
        
        # Backup current clipboard
        try:
            clipboard_backup = pyperclip.paste()
        except Exception:
            clipboard_backup = ""
        
        try:
            # Clean and copy new text to clipboard
            cleaned_text = text.rstrip('\n')
            pyperclip.copy(cleaned_text)
            
            # Small delay to ensure clipboard is updated
            time.sleep(0.05)
            
            # Paste using Ctrl+V
            keyboard = pykeyboard.Controller()
            keyboard.press(pykeyboard.Key.ctrl)
            keyboard.press('v')
            keyboard.release('v')
            keyboard.release(pykeyboard.Key.ctrl)
            
            # Wait for paste to complete
            time.sleep(0.1)
            
            # Restore original clipboard
            pyperclip.copy(clipboard_backup)
            
            logging.debug(f'Pasted {len(cleaned_text)} chars instantly')
            return True
            
        except Exception as e:
            logging.error(f"Error pasting text: {e}")
            # Try to restore clipboard
            try:
                pyperclip.copy(clipboard_backup)
            except Exception:
                pass
            return False
    
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
                    print(f"[AI Response] Streaming to active field... [{self.abort_hotkey.title()} to abort]")
                    
                    # Start abort listener and typing indicator
                    self._start_abort_listener()
                    from .core import show_typing_indicator, dismiss_typing_indicator
                    show_typing_indicator(self.abort_hotkey)
                    
                    # Buffer to accumulate chunks before typing (helps with Unicode)
                    chunk_buffer = []
                    buffer_size = 0
                    MIN_BUFFER_CHARS = 20  # Accumulate at least 20 chars before typing
                    typing_aborted = False
                    
                    def type_chunk(chunk):
                        """Buffer chunks and type when buffer is large enough"""
                        nonlocal chunk_buffer, buffer_size, typing_aborted
                        
                        # Check if aborted
                        if self.streaming_aborted or typing_aborted:
                            return
                        
                        chunk_buffer.append(chunk)
                        buffer_size += len(chunk)
                        
                        # Type when buffer reaches minimum size
                        if buffer_size >= MIN_BUFFER_CHARS:
                            text_to_type = ''.join(chunk_buffer)
                            chunk_buffer.clear()
                            buffer_size = 0
                            if not self._type_text_chunk(text_to_type):
                                typing_aborted = True
                    
                    try:
                        from ..request_pipeline import RequestOrigin
                        response, error = self._call_api(messages, on_chunk=type_chunk, origin_override=RequestOrigin.POPUP_INPUT)
                        
                        # Type any remaining buffered text (unless aborted)
                        if chunk_buffer and not self.streaming_aborted and not typing_aborted:
                            self._type_text_chunk(''.join(chunk_buffer))
                    finally:
                        # Always clean up abort listener and indicator
                        self._stop_abort_listener()
                        dismiss_typing_indicator()
                    
                    if self.streaming_aborted or typing_aborted:
                        print(f"\n⚠️ Streaming aborted by user")
                else:
                    # Non-streaming: get full response then paste instantly
                    from ..request_pipeline import RequestOrigin
                    response, error = self._call_api(messages, origin_override=RequestOrigin.POPUP_INPUT)
                    
                    # Paste the full response instantly using clipboard
                    if response and not error:
                        print(f"[Pasting to active field...]")
                        self._paste_text_instant(response)
                
                if error:
                    logging.error(f'Direct chat failed: {error}')
                    print(f"  [Error] {error}")
                    self.is_processing = False
                    return
                
                if streaming_enabled and not self.streaming_aborted:
                    print(f"\n✅ Response streamed ({len(response) if response else 0} chars)")
                elif not streaming_enabled:
                    print(f"✅ Response pasted ({len(response) if response else 0} chars)")
            
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
                   {text_delimiter_close}
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
            text_delimiter = self._get_setting("text_delimiter", "\n\n<text_to_process>\n")
            text_delimiter_close = self._get_setting("text_delimiter_close", "\n</text_to_process>")
            
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
            user_message += text_delimiter + selected_text + text_delimiter_close
            
            logging.debug(f'Getting AI response for {option_key}')
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
            
            from ..request_pipeline import RequestOrigin
            
            if show_in_chat_window:
                # For GUI mode, stream to console then show window
                print(f"\n{'─'*60}")
                print(f"[AI Response]...")
                
                response, error = self._call_api(messages, origin_override=RequestOrigin.POPUP_PROMPT)
                
                if error:
                    logging.error(f'Option processing failed: {error}')
                    print(f"  [Error] {error}")
                    self.is_processing = False
                    return
                
                if not response:
                    logging.error('No response from AI')
                    self.is_processing = False
                    return
                
                self._show_chat_window(f"{option_key} Result", response, selected_text)
                print(f"{'─'*60}\n")
            else:
                # Replace mode: type response to active field (same as direct chat)
                streaming_enabled = self.config.get("streaming_enabled", True)
                
                if streaming_enabled:
                    print(f"[AI Response] Streaming to active field... [{self.abort_hotkey.title()} to abort]")
                    
                    # Start abort listener and typing indicator
                    self._start_abort_listener()
                    from .core import show_typing_indicator, dismiss_typing_indicator
                    show_typing_indicator(self.abort_hotkey)
                    
                    # Buffer to accumulate chunks before typing (helps with Unicode)
                    chunk_buffer = []
                    buffer_size = 0
                    MIN_BUFFER_CHARS = 20  # Accumulate at least 20 chars before typing
                    typing_aborted = False
                    
                    def type_chunk(chunk):
                        """Buffer chunks and type when buffer is large enough"""
                        nonlocal chunk_buffer, buffer_size, typing_aborted
                        
                        # Check if aborted
                        if self.streaming_aborted or typing_aborted:
                            return
                        
                        chunk_buffer.append(chunk)
                        buffer_size += len(chunk)
                        
                        # Type when buffer reaches minimum size
                        if buffer_size >= MIN_BUFFER_CHARS:
                            text_to_type = ''.join(chunk_buffer)
                            chunk_buffer.clear()
                            buffer_size = 0
                            if not self._type_text_chunk(text_to_type):
                                typing_aborted = True
                    
                    try:
                        response, error = self._call_api(messages, on_chunk=type_chunk, origin_override=RequestOrigin.POPUP_PROMPT)
                        
                        # Type any remaining buffered text (unless aborted)
                        if chunk_buffer and not self.streaming_aborted and not typing_aborted:
                            self._type_text_chunk(''.join(chunk_buffer))
                    finally:
                        # Always clean up abort listener and indicator
                        self._stop_abort_listener()
                        dismiss_typing_indicator()
                    
                    if self.streaming_aborted or typing_aborted:
                        print(f"\n⚠️ Streaming aborted by user")
                else:
                    # Non-streaming: get full response then paste instantly
                    response, error = self._call_api(messages, origin_override=RequestOrigin.POPUP_PROMPT)
                    
                    # Paste the full response instantly using clipboard
                    if response and not error:
                        print(f"[Pasting to active field...]")
                        self._paste_text_instant(response)
                
                if error:
                    logging.error(f'Option processing failed: {error}')
                    print(f"  [Error] {error}")
                    self.is_processing = False
                    return
                
                if not response:
                    logging.error('No response from AI')
                    self.is_processing = False
                    return
                
                if streaming_enabled and not self.streaming_aborted:
                    print(f"\n✅ Response streamed ({len(response) if response else 0} chars)")
                elif not streaming_enabled:
                    print(f"✅ Response pasted ({len(response) if response else 0} chars)")
            
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
