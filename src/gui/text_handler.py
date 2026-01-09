#!/usr/bin/env python3
"""
Text selection and clipboard handler
"""

import ctypes
import logging
import time
from typing import Optional

import pyperclip
from pynput import keyboard as pykeyboard


class TextHandler:
    """
    Handles text selection capture and clipboard operations.
    """
    
    def __init__(self):
        self.keyboard = pykeyboard.Controller()
        logging.debug('TextHandler initialized')
    
    def get_selected_text(self, sleep_duration: float = 0.01, max_wait: float = 0.4) -> str:
        """
        Get the currently selected text from any application using polling.
        Uses Windows clipboard sequence number to detect changes without modifying clipboard history.
        
        Args:
            sleep_duration: Short delay before Ctrl+C for stability (default: 0.01s)
            max_wait: Maximum time to wait for clipboard content (default: 0.4s)
            
        Returns:
            The selected text, or empty string if none
        """
        # Backup the clipboard in case we need to restore it
        # We only restore if we actually successfully copied new text (overwriting the user's clipboard)
        try:
            clipboard_backup = pyperclip.paste()
        except Exception:
            clipboard_backup = ""
            
        # Get current sequence number to detect changes
        try:
            user32 = ctypes.windll.user32
            start_sequence = user32.GetClipboardSequenceNumber()
        except Exception as e:
            logging.error(f"Failed to get clipboard sequence: {e}")
            return ""
        
        # Short stability delay before pressing keys
        time.sleep(sleep_duration)
        
        try:
            # logging.debug('Simulating Ctrl+C')
            self.keyboard.press(pykeyboard.Key.ctrl)
            self.keyboard.press('c')
            self.keyboard.release('c')
            self.keyboard.release(pykeyboard.Key.ctrl)
        except Exception as e:
            logging.error(f'Failed to simulate Ctrl+C: {e}')
            return ""
        
        # Poll for clipboard update
        # We check frequently (every 10ms) to return as fast as possible
        start_time = time.time()
        selected_text = ""
        clipboard_changed = False
        
        while (time.time() - start_time) < max_wait:
            try:
                current_sequence = user32.GetClipboardSequenceNumber()
                if current_sequence != start_sequence:
                    selected_text = pyperclip.paste()
                    clipboard_changed = True
                    break
            except Exception:
                pass
            time.sleep(0.01)  # 10ms poll interval
            
        # If we successfully captured text, it means we overwrote the user's clipboard.
        # We should restore the original content to be transparent.
        if clipboard_changed:
            try:
                # Add a tiny delay to ensure the system is ready for another clipboard op
                # (prevent "OpenClipboard Failed" errors)
                time.sleep(0.05)
                pyperclip.copy(clipboard_backup)
            except Exception as e:
                logging.error(f'Failed to restore clipboard: {e}')
        
        return selected_text
    
    def get_selected_text_with_retry(self) -> str:
        """
        Get selected text with a retry using longer wait time.
        
        Returns:
            The selected text, or empty string if none
        """
        # First attempt with default settings (0.5s max wait)
        selected_text = self.get_selected_text()
        
        # Retry with longer wait if no text captured
        if not selected_text:
            logging.debug('No text captured, retrying with longer wait')
            # Increase stability delay and max wait
            selected_text = self.get_selected_text(sleep_duration=0.1, max_wait=0.8)
        
        return selected_text
    
    def replace_selected_text(self, new_text: str) -> bool:
        """
        Replace the currently selected text with new text.
        
        Args:
            new_text: The text to paste
            
        Returns:
            True if successful, False otherwise
        """
        if not new_text:
            return False
        
        # Backup clipboard
        try:
            clipboard_backup = pyperclip.paste()
        except Exception:
            clipboard_backup = ""
        
        try:
            # Copy new text to clipboard
            cleaned_text = new_text.rstrip('\n')
            pyperclip.copy(cleaned_text)
            
            # Simulate Ctrl+V
            time.sleep(0.1)
            self.keyboard.press(pykeyboard.Key.ctrl)
            self.keyboard.press('v')
            self.keyboard.release('v')
            self.keyboard.release(pykeyboard.Key.ctrl)
            
            time.sleep(0.2)
            
            # Restore clipboard
            pyperclip.copy(clipboard_backup)
            
            logging.debug('Text replaced successfully')
            return True
            
        except Exception as e:
            logging.error(f'Failed to replace text: {e}')
            # Try to restore clipboard
            try:
                pyperclip.copy(clipboard_backup)
            except Exception:
                pass
            return False
    
    @staticmethod
    def clear_clipboard():
        """Clear the system clipboard."""
        try:
            pyperclip.copy('')
        except Exception as e:
            logging.error(f'Error clearing clipboard: {e}')
    
    @staticmethod
    def copy_to_clipboard(text: str) -> bool:
        """
        Copy text to clipboard.
        
        Args:
            text: Text to copy
            
        Returns:
            True if successful
        """
        try:
            pyperclip.copy(text)
            return True
        except Exception as e:
            logging.error(f'Failed to copy to clipboard: {e}')
            return False
