#!/usr/bin/env python3
"""
Text selection and clipboard handler
"""

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
    
    def get_selected_text(self, sleep_duration: float = 0.2) -> str:
        """
        Get the currently selected text from any application.
        
        Args:
            sleep_duration: Time to wait for clipboard update
            
        Returns:
            The selected text, or empty string if none
        """
        # Backup the clipboard
        try:
            clipboard_backup = pyperclip.paste()
        except Exception:
            clipboard_backup = ""
        
        logging.debug(f'Clipboard backup: "{clipboard_backup[:50]}..." (sleep: {sleep_duration}s)')
        
        # Clear the clipboard
        self.clear_clipboard()
        
        # Simulate Ctrl+C
        logging.debug('Simulating Ctrl+C')
        time.sleep(sleep_duration)  # Short delay before pressing
        
        try:
            self.keyboard.press(pykeyboard.Key.ctrl)
            self.keyboard.press('c')
            self.keyboard.release('c')
            self.keyboard.release(pykeyboard.Key.ctrl)
        except Exception as e:
            logging.error(f'Failed to simulate Ctrl+C: {e}')
            # Restore clipboard
            try:
                pyperclip.copy(clipboard_backup)
            except Exception:
                pass
            return ""
        
        # Wait for the clipboard to update
        time.sleep(sleep_duration)
        logging.debug(f'Waited {sleep_duration}s for clipboard')
        
        # Get the selected text
        try:
            selected_text = pyperclip.paste()
        except Exception:
            selected_text = ""
        
        # Restore the clipboard
        try:
            pyperclip.copy(clipboard_backup)
        except Exception as e:
            logging.error(f'Failed to restore clipboard: {e}')
        
        return selected_text if selected_text != clipboard_backup else ""
    
    def get_selected_text_with_retry(self) -> str:
        """
        Get selected text with a retry using longer sleep duration.
        
        Returns:
            The selected text, or empty string if none
        """
        # First attempt with default sleep
        selected_text = self.get_selected_text()
        
        # Retry with longer sleep if no text captured
        if not selected_text:
            logging.debug('No text captured, retrying with longer sleep')
            selected_text = self.get_selected_text(sleep_duration=0.5)
        
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
