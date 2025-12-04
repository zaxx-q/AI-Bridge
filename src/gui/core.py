#!/usr/bin/env python3
"""
GUI core initialization and threading
"""

import queue
import threading
import time
from pathlib import Path

try:
    import dearpygui.dearpygui as dpg
    HAVE_GUI = True
except ImportError:
    HAVE_GUI = False
    dpg = None

# GUI state
GUI_QUEUE = queue.Queue()
GUI_THREAD = None
GUI_LOCK = threading.Lock()
GUI_RUNNING = False
GUI_CONTEXT_CREATED = False
GUI_SHUTDOWN_REQUESTED = False
OPEN_WINDOWS = set()
OPEN_WINDOWS_LOCK = threading.Lock()
WINDOW_COUNTER = 0
WINDOW_COUNTER_LOCK = threading.Lock()

# Fonts
DEFAULT_FONT = None
FONTS = {
    "regular": None,
    "bold": None,
    "italic": None,
    "bold_italic": None,
    "header1": None,
    "header2": None,
    "code": None
}


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


def init_dearpygui():
    """Initialize Dear PyGui context and viewport"""
    global GUI_CONTEXT_CREATED, DEFAULT_FONT, FONTS
    
    if not HAVE_GUI:
        return False
    
    if GUI_CONTEXT_CREATED:
        return True
    
    try:
        dpg.create_context()
        dpg.create_viewport(title='AI Bridge', width=900, height=700, decorated=True)
        
        # Create a font registry with a larger default font and styles
        with dpg.font_registry():
            # Try to load Consolas family (Windows)
            base_path = Path("C:/Windows/Fonts")
            if (base_path / "consola.ttf").exists():
                try:
                    FONTS["regular"] = dpg.add_font(str(base_path / "consola.ttf"), 16)
                    FONTS["bold"] = dpg.add_font(str(base_path / "consolab.ttf"), 16)
                    FONTS["italic"] = dpg.add_font(str(base_path / "consolai.ttf"), 16)
                    FONTS["bold_italic"] = dpg.add_font(str(base_path / "consolaz.ttf"), 16)
                    FONTS["header1"] = dpg.add_font(str(base_path / "consolab.ttf"), 26)
                    FONTS["header2"] = dpg.add_font(str(base_path / "consolab.ttf"), 20)
                    FONTS["code"] = dpg.add_font(str(base_path / "consola.ttf"), 14)
                    DEFAULT_FONT = FONTS["regular"]
                except Exception as e:
                    print(f"[GUI Warning] Failed to load Consolas fonts: {e}")

            # Fallback if Consolas failed or not on Windows
            if not DEFAULT_FONT:
                font_paths = [
                    "C:/Windows/Fonts/segoeui.ttf",  # Windows Segoe UI
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",  # Linux
                    "/System/Library/Fonts/SFNSMono.ttf",  # macOS
                    "/System/Library/Fonts/Menlo.ttc",  # macOS fallback
                ]
                
                for font_path in font_paths:
                    if Path(font_path).exists():
                        try:
                            DEFAULT_FONT = dpg.add_font(font_path, 16)
                            FONTS["regular"] = DEFAULT_FONT
                            # Create larger variants for headers if possible
                            FONTS["header1"] = dpg.add_font(font_path, 26)
                            FONTS["header2"] = dpg.add_font(font_path, 20)
                            break
                        except:
                            continue
            
            if DEFAULT_FONT:
                dpg.bind_font(DEFAULT_FONT)
        
        # Set theme
        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 6)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 6)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 6)
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (30, 30, 40))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (45, 45, 60))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (70, 100, 150))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (90, 120, 170))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (60, 90, 140))
        
        dpg.bind_theme(global_theme)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        GUI_CONTEXT_CREATED = True
        return True
    except Exception as e:
        print(f"[GUI Error] Failed to initialize Dear PyGui: {e}")
        return False


def shutdown_dearpygui():
    """Shutdown Dear PyGui context"""
    global GUI_CONTEXT_CREATED, GUI_RUNNING, DEFAULT_FONT
    
    try:
        if GUI_CONTEXT_CREATED:
            dpg.destroy_context()
            GUI_CONTEXT_CREATED = False
            DEFAULT_FONT = None
            with OPEN_WINDOWS_LOCK:
                OPEN_WINDOWS.clear()
    except Exception as e:
        print(f"[GUI Error] Failed to shutdown Dear PyGui: {e}")
    
    GUI_RUNNING = False


def gui_main_loop():
    """Main GUI loop running in separate thread - runs only when windows are open"""
    global GUI_RUNNING, GUI_SHUTDOWN_REQUESTED
    
    if not init_dearpygui():
        print("[GUI Error] Failed to start GUI")
        GUI_RUNNING = False
        return
    
    GUI_RUNNING = True
    GUI_SHUTDOWN_REQUESTED = False
    last_window_check = time.time()
    
    print("[GUI] Started")
    
    while dpg.is_dearpygui_running() and not GUI_SHUTDOWN_REQUESTED:
        # Process any queued GUI requests
        try:
            while not GUI_QUEUE.empty():
                task = GUI_QUEUE.get_nowait()
                task_type = task.get("type")
                
                if task_type == "result":
                    from .windows import create_result_window
                    create_result_window(task["text"], task.get("endpoint"), task.get("title"))
                elif task_type == "chat":
                    from .windows import create_chat_window
                    create_chat_window(task["session"], task.get("initial_response"))
                elif task_type == "browser":
                    from .windows import create_session_browser_window
                    create_session_browser_window()
                
                GUI_QUEUE.task_done()
        except:
            pass
        
        dpg.render_dearpygui_frame()
        
        # Check if all windows are closed (every 0.5 seconds)
        current_time = time.time()
        if current_time - last_window_check > 0.5:
            last_window_check = current_time
            if not has_open_windows():
                print("[GUI] All windows closed, stopping...")
                break
    
    shutdown_dearpygui()
    print("[GUI] Stopped")


def ensure_gui_running():
    """Ensure GUI thread is running, start if needed"""
    global GUI_THREAD, GUI_RUNNING, GUI_SHUTDOWN_REQUESTED
    
    if not HAVE_GUI:
        return False
    
    with GUI_LOCK:
        if GUI_RUNNING and GUI_THREAD and GUI_THREAD.is_alive():
            return True
        
        # Start new GUI thread
        GUI_SHUTDOWN_REQUESTED = False
        GUI_THREAD = threading.Thread(target=gui_main_loop, daemon=True)
        GUI_THREAD.start()
        
        # Wait for GUI to initialize
        for _ in range(50):  # Wait up to 5 seconds
            if GUI_RUNNING and GUI_CONTEXT_CREATED:
                return True
            time.sleep(0.1)
        
        return GUI_RUNNING


def show_result_gui(text, title="AI Response", endpoint=None):
    """Queue a result GUI window to be created"""
    if not HAVE_GUI:
        print("[Warning] GUI not available.")
        return False
    
    if not ensure_gui_running():
        print("[Warning] Failed to start GUI.")
        return False
    
    GUI_QUEUE.put({"type": "result", "text": text, "title": title, "endpoint": endpoint})
    return True


def show_chat_gui(session, initial_response=None):
    """Queue a chat GUI window to be created"""
    if not HAVE_GUI:
        print("[Warning] GUI not available.")
        return False
    
    if not ensure_gui_running():
        print("[Warning] Failed to start GUI.")
        return False
    
    GUI_QUEUE.put({"type": "chat", "session": session, "initial_response": initial_response})
    return True


def show_session_browser():
    """Queue a session browser window to be created"""
    if not HAVE_GUI:
        print("[Warning] GUI not available.")
        return False
    
    if not ensure_gui_running():
        print("[Warning] Failed to start GUI.")
        return False
    
    GUI_QUEUE.put({"type": "browser"})
    return True


def get_gui_status():
    """Get current GUI status"""
    return {
        "available": HAVE_GUI,
        "running": GUI_RUNNING,
        "context_created": GUI_CONTEXT_CREATED,
        "open_windows": len(OPEN_WINDOWS)
    }
