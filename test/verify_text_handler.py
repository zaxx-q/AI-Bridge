#!/usr/bin/env python3
"""
Verification script for TextHandler optimization.
Mocks environment to test polling logic and edge cases.
"""

import sys
import time
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
import os
sys.path.append(os.getcwd())

from src.gui.text_handler import TextHandler

class TestTextHandlerOptimization(unittest.TestCase):
    
    def setUp(self):
        # Mock pynput Controller
        self.keyboard_patcher = patch('src.gui.text_handler.pykeyboard.Controller')
        self.MockKeyboard = self.keyboard_patcher.start()
        self.mock_keyboard_instance = self.MockKeyboard.return_value
        
        # Mock pyperclip
        self.clipboard_patcher = patch('src.gui.text_handler.pyperclip')
        self.mock_clipboard = self.clipboard_patcher.start()
        
        self.handler = TextHandler()
        
    def tearDown(self):
        self.keyboard_patcher.stop()
        self.clipboard_patcher.stop()
        
    def test_immediate_success(self):
        """Test getting text when clipboard updates immediately"""
        print("\nTesting: Immediate Success")
        
        # Setup: Initial clipboard -> Cleared -> New Content
        # side_effect controls return values of successive calls
        self.mock_clipboard.paste.side_effect = [
            "old_content",  # backup
            "new_selection" # poll check
        ]
        
        start_time = time.time()
        result = self.handler.get_selected_text(sleep_duration=0.01, max_wait=0.5)
        duration = time.time() - start_time
        
        print(f"Result: '{result}', Duration: {duration:.3f}s")
        self.assertEqual(result, "new_selection")
        # Should be very fast (close to sleep_duration + minimal overhead)
        self.assertLess(duration, 0.2)
        
    def test_delayed_success(self):
        """Test getting text when clipboard updates after delay (polling works)"""
        print("\nTesting: Delayed Success (Polling)")
        
        # Setup: Initial -> Cleared -> Empty -> Empty -> Content
        self.mock_clipboard.paste.side_effect = [
            "old_content", # backup
            "",            # poll 1
            "",            # poll 2
            "delayed_text" # poll 3 (success)
        ]
        
        start_time = time.time()
        result = self.handler.get_selected_text(sleep_duration=0.01, max_wait=0.5)
        duration = time.time() - start_time
        
        print(f"Result: '{result}', Duration: {duration:.3f}s")
        self.assertEqual(result, "delayed_text")
        # Should take a bit longer but definitely less than max_wait
        self.assertLess(duration, 0.5)
        self.assertGreater(duration, 0.01)
        
    def test_no_selection_timeout(self):
        """Test timeout when no text is selected"""
        print("\nTesting: No Selection (Timeout)")
        
        # Setup: Always return empty after clear
        def paste_mock():
            return ""
        self.mock_clipboard.paste.side_effect = paste_mock
        
        # But we need to handle the initial backup call differently?
        # Actually side_effect with callable replaces the list approach
        # Let's use list with many empty strings to simulate timeout
        # 1 backup + 100 polls
        self.mock_clipboard.paste.side_effect = ["backup"] + [""] * 100
        
        start_time = time.time()
        # Short timeout for test
        result = self.handler.get_selected_text(sleep_duration=0.01, max_wait=0.1)
        duration = time.time() - start_time
        
        print(f"Result: '{result}', Duration: {duration:.3f}s")
        self.assertEqual(result, "")
        # Should persist until max_wait
        self.assertGreaterEqual(duration, 0.1)
        
    def test_same_text_bug_fix(self):
        """Test that selecting text identical to clipboard is now detected (Bug Fix)"""
        print("\nTesting: Same Text Detection (Bug Fix)")
        
        target_text = "same_old_text"
        
        # Original code would fail this because result == backup
        # New code clears clipboard first, so it sees "same_old_text" appear from empty
        self.mock_clipboard.paste.side_effect = [
            target_text,  # backup is same
            target_text   # found same text
        ]
        
        start_time = time.time()
        result = self.handler.get_selected_text(sleep_duration=0.01, max_wait=0.5)
        duration = time.time() - start_time
        
        print(f"Result: '{result}', Duration: {duration:.3f}s")
        self.assertEqual(result, target_text)

if __name__ == '__main__':
    unittest.main()