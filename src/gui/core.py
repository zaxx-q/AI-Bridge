#!/usr/bin/env python3
"""
GUI core initialization and threading - Tkinter implementation
"""

import queue
import threading
import time
import tkinter as tk
from typing import Optional

# Tkinter is always available in standard Python
HAVE_GUI = True

# GUI state
GUI_QUEUE = queue.Queue()
GUI_THREAD: Optional[threading.Thread] = None
GUI_LOCK = threading.Lock()
GUI_RUNNING = False
GUI_ROOT: Optional[tk.Tk] = None
GUI_SHUTDOWN_REQUESTED = False

# Track open windows
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


def schedule_gui_task(task_func):
    """Schedule a task to run on the GUI thread"""
    global GUI_ROOT
    if GUI_ROOT and GUI_RUNNING:
        try:
            GUI_ROOT.after(0, task_func)
        except tk.TclError:
            pass


def init_tkinter():
    """Initialize the hidden Tkinter root window"""
    global GUI_ROOT
    
    try:
        GUI_ROOT = tk.Tk()
        GUI_ROOT.withdraw()  # Hide the root window
        GUI_ROOT.title("AI Bridge GUI")
        return True
    except Exception as e:
        print(f"[GUI Error] Failed to initialize Tkinter: {e}")
        return False


def shutdown_tkinter():
    """Shutdown Tkinter context"""
    global GUI_ROOT, GUI_RUNNING
    
    try:
        if GUI_ROOT:
            GUI_ROOT.quit()
            GUI_ROOT.destroy()
            GUI_ROOT = None
    except Exception as e:
        print(f"[GUI Error] Failed to shutdown Tkinter: {e}")
    
    GUI_RUNNING = False
    with OPEN_WINDOWS_LOCK:
        OPEN_WINDOWS.clear()


def process_gui_queue():
    """Process queued GUI tasks"""
    global GUI_ROOT
    
    if not GUI_ROOT:
        return
    
    try:
        while not GUI_QUEUE.empty():
            task = GUI_QUEUE.get_nowait()
            task_type = task.get("type")
            
            if task_type == "chat":
                from .windows import create_chat_window
                create_chat_window(task["session"], task.get("initial_response"))
            elif task_type == "browser":
                from .windows import create_session_browser_window
                create_session_browser_window()
            
            GUI_QUEUE.task_done()
    except Exception as e:
        print(f"[GUI Error] Failed to process queue: {e}")


def check_windows_and_schedule():
    """Check windows periodically and continue processing"""
    global GUI_ROOT, GUI_SHUTDOWN_REQUESTED
    
    if not GUI_ROOT or GUI_SHUTDOWN_REQUESTED:
        return
    
    # Process any queued tasks
    process_gui_queue()
    
    # Check if all windows are closed
    if not has_open_windows():
        # Wait a bit more before shutting down (allow for new windows)
        GUI_ROOT.after(500, check_shutdown)
    else:
        # Schedule next check
        GUI_ROOT.after(100, check_windows_and_schedule)


def check_shutdown():
    """Check if we should shutdown (no windows for a period)"""
    global GUI_ROOT, GUI_SHUTDOWN_REQUESTED
    
    if not GUI_ROOT:
        return
    
    # Process any queued tasks first
    process_gui_queue()
    
    if not has_open_windows() and GUI_QUEUE.empty():
        print("[GUI] All windows closed, stopping...")
        GUI_SHUTDOWN_REQUESTED = True
        shutdown_tkinter()
    else:
        # Continue checking
        GUI_ROOT.after(100, check_windows_and_schedule)


def gui_main_loop():
    """Main GUI loop running in separate thread"""
    global GUI_RUNNING, GUI_SHUTDOWN_REQUESTED
    
    if not init_tkinter():
        print("[GUI Error] Failed to start GUI")
        GUI_RUNNING = False
        return
    
    GUI_RUNNING = True
    GUI_SHUTDOWN_REQUESTED = False
    
    print("[GUI] Started")
    
    # Start processing queue and checking windows
    GUI_ROOT.after(100, check_windows_and_schedule)
    
    try:
        GUI_ROOT.mainloop()
    except Exception as e:
        print(f"[GUI Error] Main loop error: {e}")
    finally:
        GUI_RUNNING = False
        print("[GUI] Stopped")


def ensure_gui_running():
    """Ensure GUI thread is running, start if needed"""
    global GUI_THREAD, GUI_RUNNING, GUI_SHUTDOWN_REQUESTED
    
    with GUI_LOCK:
        if GUI_RUNNING and GUI_THREAD and GUI_THREAD.is_alive():
            return True
        
        # Start new GUI thread
        GUI_SHUTDOWN_REQUESTED = False
        GUI_THREAD = threading.Thread(target=gui_main_loop, daemon=True)
        GUI_THREAD.start()
        
        # Wait for GUI to initialize
        for _ in range(50):  # Wait up to 5 seconds
            if GUI_RUNNING and GUI_ROOT:
                return True
            time.sleep(0.1)
        
        return GUI_RUNNING


def show_chat_gui(session, initial_response=None):
    """Queue a chat GUI window to be created"""
    if not ensure_gui_running():
        print("[Warning] Failed to start GUI.")
        return False
    
    GUI_QUEUE.put({"type": "chat", "session": session, "initial_response": initial_response})
    
    # Trigger queue processing
    schedule_gui_task(process_gui_queue)
    return True


def show_session_browser():
    """Queue a session browser window to be created"""
    if not ensure_gui_running():
        print("[Warning] Failed to start GUI.")
        return False
    
    GUI_QUEUE.put({"type": "browser"})
    
    # Trigger queue processing
    schedule_gui_task(process_gui_queue)
    return True


def get_gui_status():
    """Get current GUI status"""
    return {
        "available": HAVE_GUI,
        "running": GUI_RUNNING,
        "context_created": GUI_ROOT is not None,
        "open_windows": len(OPEN_WINDOWS)
    }
