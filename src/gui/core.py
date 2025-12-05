#!/usr/bin/env python3
"""
GUI core initialization and threading - Tkinter implementation

This module provides a simple approach where each window type creates
its own Tk root and runs its own mainloop in a thread, avoiding the
threading issues with shared Tk roots.
"""

import threading
import time
from typing import Optional

# Tkinter is always available in standard Python
HAVE_GUI = True

# Track open windows for status
OPEN_WINDOWS = set()
OPEN_WINDOWS_LOCK = threading.Lock()
WINDOW_COUNTER = 0
WINDOW_COUNTER_LOCK = threading.Lock()


def get_next_window_id():
    """Get next unique window ID"""
    global WINDOW_COUNTER
    with WINDOW_COUNTER_LOCK:
        WINDOW_COUNTER += 1
        return WINDOW_COUNTER


def register_window(window_tag):
    """Register a window as open"""
    with OPEN_WINDOWS_LOCK:
        OPEN_WINDOWS.add(window_tag)


def unregister_window(window_tag):
    """Unregister a window when closed"""
    with OPEN_WINDOWS_LOCK:
        OPEN_WINDOWS.discard(window_tag)


def has_open_windows():
    """Check if any windows are open"""
    with OPEN_WINDOWS_LOCK:
        return len(OPEN_WINDOWS) > 0


def show_chat_gui(session, initial_response=None):
    """Show a chat GUI window in a new thread with its own Tk root"""
    def run_chat_window():
        from .windows import StandaloneChatWindow
        window = StandaloneChatWindow(session, initial_response)
        window.show()
    
    thread = threading.Thread(target=run_chat_window, daemon=True)
    thread.start()
    return True


def show_session_browser():
    """Show a session browser window in a new thread with its own Tk root"""
    def run_browser_window():
        from .windows import StandaloneSessionBrowserWindow
        window = StandaloneSessionBrowserWindow()
        window.show()
    
    thread = threading.Thread(target=run_browser_window, daemon=True)
    thread.start()
    return True


def get_gui_status():
    """Get current GUI status"""
    return {
        "available": HAVE_GUI,
        "running": has_open_windows(),
        "open_windows": len(OPEN_WINDOWS)
    }
