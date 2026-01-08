import time
import tkinter as tk
try:
    import customtkinter as ctk
except ImportError:
    print("CTK not installed, skipping test")
    import sys
    sys.exit(0)

class SettingsWindow:
    def __init__(self):
        self.root = ctk.CTk()
        
        # Suppress specific Tcl errors
        def report_callback_exception(self, exc, val, tb):
            import traceback
            err = traceback.format_exception_only(exc, val)[0]
            if "invalid command name" in err:
                return
            print("Error:", err)
            
        self.root.report_callback_exception = report_callback_exception
        
        self.root.geometry("200x200")
        self._destroyed = False
        
        # Add some after callbacks
        self.root.after(500, self.some_task)
        self.root.after(1000, self.close)
        
    def some_task(self):
        if not self._destroyed:
            print("Running task")
            self.root.after(100, self.some_task)

    def close(self):
        print("Closing...")
        self._destroyed = True
        self.root.destroy()
        self.root = None
        print("Closed.")

    def run(self):
        print("Starting loop")
        while self.root is not None and not self._destroyed:
            try:
                self.root.update()
                time.sleep(0.01)
            except tk.TclError:
                break
        print("Loop finished")

if __name__ == "__main__":
    win = SettingsWindow()
    win.run()