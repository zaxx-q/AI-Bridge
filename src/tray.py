#!/usr/bin/env python3
"""
System Tray implementation for AI Bridge
Uses infi.systray for Windows with native .ico support (no Pillow needed)
"""

import os
import sys
import shutil
import subprocess
import ctypes
from pathlib import Path
import threading

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


def disable_console_close_button():
    """
    Disable the close button (X) on the console window.
    This prevents users from accidentally closing the app via the console.
    They should use the tray icon's Quit option instead.
    """
    if sys.platform != 'win32':
        return False
    
    try:
        hwnd = get_console_window()
        if not hwnd:
            return False
        
        # Get the system menu (window menu)
        # GetSystemMenu(hwnd, bRevert) - bRevert=False gets the current menu
        user32 = ctypes.windll.user32
        hmenu = user32.GetSystemMenu(hwnd, False)
        
        if hmenu:
            # SC_CLOSE = 0xF060
            # MF_BYCOMMAND = 0x0000
            # MF_GRAYED = 0x0001
            # DeleteMenu or EnableMenuItem to disable close
            SC_CLOSE = 0xF060
            MF_BYCOMMAND = 0x0000
            MF_GRAYED = 0x0001
            
            # Disable (gray out) the close menu item
            user32.EnableMenuItem(hmenu, SC_CLOSE, MF_BYCOMMAND | MF_GRAYED)
            
            # Also remove it entirely (optional - comment out if you just want grayed)
            # user32.DeleteMenu(hmenu, SC_CLOSE, MF_BYCOMMAND)
            
            return True
    except Exception as e:
        print(f"[Warning] Could not disable console close button: {e}")
    
    return False


def enable_console_close_button():
    """Re-enable the close button on the console window."""
    if sys.platform != 'win32':
        return False
    
    try:
        hwnd = get_console_window()
        if not hwnd:
            return False
        
        user32 = ctypes.windll.user32
        # GetSystemMenu with bRevert=True resets to default
        user32.GetSystemMenu(hwnd, True)
        return True
    except Exception:
        pass
    
    return False


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
        script = os.path.abspath(sys.argv[0])
        args = sys.argv[1:]
        
        # Ensure console is shown before restart
        show_console()
        enable_console_close_button()  # Re-enable close button before restart
        
        # Start the new process FIRST, before doing anything that might fail
        if sys.platform == 'win32':
            try:
                # Check for Windows Terminal
                wt_path = shutil.which("wt.exe")
                
                # Check if we should prevent WT launch (e.g. user set flag)
                no_wt = "--no-wt" in args
                
                if wt_path and not no_wt:
                    # Launch in Windows Terminal
                    print("🔄 Restarting via Windows Terminal...")
                    env = os.environ.copy()
                    env["AI_BRIDGE_WT_LAUNCHED"] = "1"  # Prevent loop
                    
                    cmd = [wt_path, "-w", "0", "-d", os.getcwd()]
                    if script.endswith('.py'):
                        cmd.extend([sys.executable, script] + args)
                    else:
                        cmd.extend([script] + args)
                        
                    subprocess.Popen(cmd, env=env, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                    
                else:
                    # Legacy console restart
                    # DETACHED_PROCESS = 0x00000008
                    # CREATE_NEW_CONSOLE = 0x00000010
                    # CREATE_NEW_PROCESS_GROUP = 0x00000200
                    flags = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
                    
                    if script.endswith('.py'):
                        subprocess.Popen(
                            [sys.executable, script] + args,
                            creationflags=flags,
                            start_new_session=True
                        )
                    else:
                        # Frozen executable
                        subprocess.Popen(
                            [script] + args,
                            creationflags=flags,
                            start_new_session=True
                        )
            except Exception as e:
                print(f"[Error] Failed to start new process: {e}")
                return  # Don't exit if we couldn't start new process
        else:
            os.execv(sys.executable, [sys.executable, script] + args)
        
        # Don't call systray.shutdown() - it causes "cannot join current thread" error
        # Just force exit. The tray icon will disappear when the process dies.
        os._exit(0)
    
    def _on_session_browser(self, systray):
        """Open the session browser GUI"""
        try:
            from .gui.core import show_session_browser, HAVE_GUI
            if HAVE_GUI:
                show_session_browser()
            else:
                print("[Warning] GUI not available")
        except Exception as e:
            print(f"[Error] Could not open session browser: {e}")
    
    def _on_settings(self, systray):
        """Open settings window"""
        try:
            from .gui.core import show_settings_window, HAVE_GUI
            if HAVE_GUI:
                print("\n⚙️  Opening settings...\n")
                show_settings_window()
            else:
                print("[Warning] GUI not available")
        except Exception as e:
            print(f"[Error] Could not open settings: {e}")
    
    def _on_prompt_editor(self, systray):
        """Open prompt editor window"""
        try:
            from .gui.core import show_prompt_editor, HAVE_GUI
            if HAVE_GUI:
                print("\n✏️  Opening prompt editor...\n")
                show_prompt_editor()
            else:
                print("[Warning] GUI not available")
        except Exception as e:
            print(f"[Error] Could not open prompt editor: {e}")
    
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
        enable_console_close_button()  # Re-enable close button before exit
        
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
        
        # Disable the console close button (X) to prevent accidental closure
        # Users should use tray icon's Quit option instead
        disable_console_close_button()
        
        # Enable dark mode for menus if applicable
        self._enable_dark_mode()
        
        # Define menu options
        # Format: (text, icon, callback)
        menu_options = (
            ("Toggle Console", None, self._on_toggle_console),
            ("Session Browser", None, self._on_session_browser),
            ("Settings", None, self._on_settings),
            ("Prompt Editor", None, self._on_prompt_editor),
            ("Edit config.ini (file)", None, self._on_edit_config),
            ("Edit prompts.json (file)", None, self._on_edit_options),
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
    
    def _enable_dark_mode(self):
        """
        Attempt to enable dark mode for the application menus.
        Uses undocumented Windows APIs.
        """
        if sys.platform != 'win32':
            return
            
        try:
            # Check if we should use dark mode
            try:
                from .gui.themes import is_dark_mode
                should_be_dark = is_dark_mode()
            except ImportError:
                should_be_dark = True # Default to dark if can't check
            
            if not should_be_dark:
                return

            # uxtheme.dll ordinal 135 is SetPreferredAppMode (Windows 10 1903+)
            # 0 = Default, 1 = AllowDark, 2 = ForceDark, 3 = ForceLight, 4 = Max
            try:
                uxtheme = ctypes.windll.uxtheme
                # Try to load the function by ordinal
                if hasattr(uxtheme, "SetPreferredAppMode"):
                    uxtheme.SetPreferredAppMode(2) # Force Dark
                else:
                    # Try by ordinal for older versions or if not exposed by name
                    try:
                        SetPreferredAppMode = uxtheme[135]
                        SetPreferredAppMode(2)
                    except Exception:
                        pass
            except Exception:
                pass
                
        except Exception as e:
            print(f"[Warning] Failed to enable dark mode for tray: {e}")

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