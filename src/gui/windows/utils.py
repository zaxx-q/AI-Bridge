#!/usr/bin/env python3
"""
Utility functions for window management.

Provides:
- get_icon_path(): Find the application icon
- set_window_icon(): Set window icon with CTk override handling
"""

import os
import sys


def get_icon_path():
    """Get the path to the application icon."""
    # Handle frozen state (executable)
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
        icon_path = os.path.join(base_dir, "icon.ico")
        if os.path.exists(icon_path):
            return icon_path
            
    # Development mode
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    icon_path = os.path.join(base_dir, "icon.ico")
    if os.path.exists(icon_path):
        return icon_path
    return None


def set_window_icon(window, delay_ms: int = 100):
    """
    Set the window icon to the AIPromptBridge icon.
    
    For CustomTkinter windows, the icon must be set AFTER the window
    is fully initialized, because CTk overrides the icon during setup.
    We use multiple after() calls to ensuring the icon persists.
    
    Args:
        window: The Tk/CTk window
        delay_ms: Initial delay (deprecated, kept for compatibility)
    """
    icon_path = get_icon_path()
    if icon_path and sys.platform == "win32":
        def _set_icon():
            try:
                if window.winfo_exists():
                    window.iconbitmap(icon_path)
            except Exception:
                pass  # Icon setting may fail on some systems
        
        # Use multiple after() calls to override CTk defaults and race conditions
        try:
            window.after(50, _set_icon)
            window.after(150, _set_icon)
            window.after(300, _set_icon)
            window.after(500, _set_icon)  # Extra check for slower systems/frozen starts
        except Exception:
            pass
