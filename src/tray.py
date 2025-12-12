#!/usr/bin/env python3
"""
System Tray implementation for AI Bridge
Uses infi.systray for Windows with native .ico support (no Pillow needed)
"""

import os
import sys
import subprocess
import ctypes
from pathlib import Path

# Try to import infi.systray
HAVE_SYSTRAY = False
SysTrayIcon = None
try:
    from infi.systray import SysTrayIcon
    HAVE_SYSTRAY = True
except ImportError:
    pass


# ─── Console Window Control (Windows) ─────────────────────────────────────────

def get_console_window():
    """Get the console window handle"""
    if sys.platform == 'win32':
        return ctypes.windll.kernel32.GetConsoleWindow()
    return None


def show_console():
    """Show the console window"""
    if sys.platform == 'win32':
        hwnd = get_console_window()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            return True
    return False


def hide_console():
    """Hide the console window"""
    if sys.platform == 'win32':
        hwnd = get_console_window()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
            return True
    return False


def is_console_visible():
    """Check if console window is currently visible"""
    if sys.platform == 'win32':
        hwnd = get_console_window()
        if hwnd:
            return ctypes.windll.user32.IsWindowVisible(hwnd)
    return True


# ─── Tray Application ─────────────────────────────────────────────────────────

class TrayApp:
    """System tray application for AI Bridge"""
    
    def __init__(self, icon_path=None, on_exit_callback=None):
        """
        Initialize the tray application
        
        Args:
            icon_path: Path to the .ico file (default: icon.ico in project root)
            on_exit_callback: Function to call when exiting
        """
        self.systray = None
        self.on_exit_callback = on_exit_callback
        self.console_visible = True
        
        # Find icon path
        if icon_path is None:
            # Look for icon.ico in the project root
            project_root = Path(__file__).parent.parent
            icon_path = project_root / "icon.ico"
            if not icon_path.exists():
                # Fallback: try current directory
                icon_path = Path("icon.ico")
        
        self.icon_path = str(icon_path) if Path(icon_path).exists() else None
        
        if not HAVE_SYSTRAY:
            print("[Warning] infi.systray not available - tray functionality disabled")
            print("         Install with: pip install infi.systray")
    
    def _on_toggle_console(self, systray):
        """Toggle console visibility"""
        if self.console_visible:
            hide_console()
            self.console_visible = False
        else:
            show_console()
            self.console_visible = True
    
    def _on_show_console(self, systray):
        """Show the console window"""
        show_console()
        self.console_visible = True
    
    def _on_hide_console(self, systray):
        """Hide the console window"""
        hide_console()
        self.console_visible = False
    
    def _on_restart(self, systray):
        """Restart the application"""
        print("\n🔄 Restarting AI Bridge...")
        
        # Get the current script path
        script = sys.argv[0]
        args = sys.argv[1:]
        
        # Ensure console is shown before restart
        show_console()
        
        # Stop the tray
        if self.systray:
            self.systray.shutdown()
        
        # Restart the process
        if sys.platform == 'win32':
            # Use subprocess to start new process
            subprocess.Popen([sys.executable, script] + args, 
                           creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            os.execv(sys.executable, [sys.executable, script] + args)
        
        # Exit current process
        os._exit(0)
    
    def _on_edit_config(self, systray):
        """Open config.ini in default editor"""
        config_path = Path(__file__).parent.parent / "config.ini"
        if config_path.exists():
            self._open_file(config_path)
        else:
            print(f"[Error] Config file not found: {config_path}")
    
    def _on_edit_options(self, systray):
        """Open text_edit_tool_options.json in default editor"""
        options_path = Path(__file__).parent.parent / "text_edit_tool_options.json"
        if options_path.exists():
            self._open_file(options_path)
        else:
            print(f"[Error] Options file not found: {options_path}")
    
    def _open_file(self, path):
        """Open a file in the default system editor"""
        path = str(path)
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.run(['open', path])
        else:
            subprocess.run(['xdg-open', path])
    
    def _on_exit(self, systray):
        """Exit the application"""
        print("\n👋 Exiting AI Bridge...")
        
        # Show console before exit so user sees the message
        show_console()
        
        # Call the exit callback if provided
        if self.on_exit_callback:
            self.on_exit_callback()
        
        # Force exit
        os._exit(0)
    
    def start(self, hide_console_on_start=True):
        """
        Start the system tray icon
        
        Args:
            hide_console_on_start: Whether to hide console when tray starts
        """
        if not HAVE_SYSTRAY:
            print("[Warning] System tray not available")
            return False
        
        if not self.icon_path:
            print("[Warning] Icon file not found - using default icon")
        
        # Define menu options
        # Format: (text, icon, callback) or (None, None, None) for separator
        menu_options = (
            ("Show Console", None, self._on_show_console),
            ("Hide Console", None, self._on_hide_console),
            (None, None, None),  # Separator
            ("Edit config.ini", None, self._on_edit_config),
            ("Edit text_edit_tool_options.json", None, self._on_edit_options),
            (None, None, None),  # Separator
            ("Restart", None, self._on_restart),
        )
        
        # Create the system tray icon
        try:
            self.systray = SysTrayIcon(
                self.icon_path,
                "AI Bridge",
                menu_options,
                on_quit=self._on_exit,
                default_menu_index=0  # "Show Console" is default action on double-click
            )
            
            # Hide console if requested
            if hide_console_on_start:
                hide_console()
                self.console_visible = False
            
            # Start the tray (this blocks until shutdown is called)
            self.systray.start()
            return True
            
        except Exception as e:
            print(f"[Error] Failed to start system tray: {e}")
            return False
    
    def stop(self):
        """Stop the system tray icon"""
        if self.systray:
            self.systray.shutdown()


def run_with_tray(main_func, icon_path=None, hide_console=True):
    """
    Wrapper to run the main application with tray support
    
    Args:
        main_func: The main function to run (should start Flask, etc.)
        icon_path: Path to icon.ico
        hide_console: Whether to hide console on start
    """
    import threading
    
    # Create tray app
    tray = TrayApp(icon_path=icon_path)
    
    if not HAVE_SYSTRAY:
        # No tray support - just run main function
        main_func()
        return
    
    # Run main function in a separate thread
    main_thread = threading.Thread(target=main_func, daemon=True)
    main_thread.start()
    
    # Start tray (this blocks)
    tray.start(hide_console_on_start=hide_console)