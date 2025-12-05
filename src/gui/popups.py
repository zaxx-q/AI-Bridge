#!/usr/bin/env python3
"""
Popup windows for TextEditTool - input and prompt selection
"""

import logging
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Dict

try:
    import darkdetect
    HAVE_DARKDETECT = True
except ImportError:
    HAVE_DARKDETECT = False


def is_dark_mode() -> bool:
    """Check if system is in dark mode."""
    if HAVE_DARKDETECT:
        try:
            return darkdetect.isDark()
        except Exception:
            pass
    return False


class BasePopup:
    """Base class for popup windows"""
    
    def __init__(self):
        self.root: Optional[tk.Tk] = None
        self.dark_mode = is_dark_mode()
        self._setup_colors()
    
    def _setup_colors(self):
        """Setup color scheme based on dark/light mode."""
        if self.dark_mode:
            self.bg_color = "#2d2d2d"
            self.fg_color = "#ffffff"
            self.button_bg = "#444444"
            self.button_hover = "#555555"
            self.input_bg = "#333333"
            self.border_color = "#666666"
            self.accent_color = "#4CAF50"
        else:
            self.bg_color = "#f5f5f5"
            self.fg_color = "#333333"
            self.button_bg = "#ffffff"
            self.button_hover = "#e8e8e8"
            self.input_bg = "#ffffff"
            self.border_color = "#cccccc"
            self.accent_color = "#4CAF50"
    
    def _close(self):
        """Close the popup window."""
        if self.root:
            self.root.destroy()
            self.root = None
    
    def is_open(self) -> bool:
        """Check if the popup is currently open."""
        return self.root is not None and self.root.winfo_exists()


class InputPopup(BasePopup):
    """
    Simple input popup for when no text is selected.
    Shows only an input field for direct AI chat.
    """
    
    def __init__(
        self,
        on_submit: Callable[[str], None],
        on_close: Optional[Callable[[], None]] = None
    ):
        super().__init__()
        self.on_submit = on_submit
        self.on_close_callback = on_close
        self.input_var: Optional[tk.StringVar] = None
    
    def show(self, x: Optional[int] = None, y: Optional[int] = None):
        """Show the input popup."""
        self.root = tk.Tk()
        self.root.withdraw()
        
        self.root.title("AI Chat")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg=self.bg_color)
        
        # Main frame with border
        main_frame = tk.Frame(
            self.root,
            bg=self.bg_color,
            highlightbackground=self.border_color,
            highlightthickness=1
        )
        main_frame.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        
        content_frame = tk.Frame(main_frame, bg=self.bg_color)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Close button
        top_bar = tk.Frame(content_frame, bg=self.bg_color)
        top_bar.pack(fill=tk.X, pady=(0, 5))
        
        close_btn = tk.Button(
            top_bar,
            text="×",
            font=("Arial", 14, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            activebackground=self.button_hover,
            relief=tk.FLAT,
            bd=0,
            command=self._close
        )
        close_btn.pack(side=tk.RIGHT)
        
        # Input area
        input_frame = tk.Frame(content_frame, bg=self.bg_color)
        input_frame.pack(fill=tk.X)
        
        self.input_var = tk.StringVar()
        placeholder = "Ask your AI..."
        
        input_entry = tk.Entry(
            input_frame,
            textvariable=self.input_var,
            font=("Arial", 11),
            bg=self.input_bg,
            fg=self.fg_color,
            insertbackground=self.fg_color,
            relief=tk.FLAT,
            highlightbackground=self.border_color,
            highlightthickness=1,
            width=40
        )
        input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5), ipady=8)
        input_entry.insert(0, placeholder)
        input_entry.config(fg='gray')
        
        def on_focus_in(event):
            if input_entry.get() == placeholder:
                input_entry.delete(0, tk.END)
                input_entry.config(fg=self.fg_color)
        
        def on_focus_out(event):
            if not input_entry.get():
                input_entry.insert(0, placeholder)
                input_entry.config(fg='gray')
        
        input_entry.bind('<FocusIn>', on_focus_in)
        input_entry.bind('<FocusOut>', on_focus_out)
        input_entry.bind('<Return>', lambda e: self._submit())
        
        # Send button
        send_btn = tk.Button(
            input_frame,
            text="➤",
            font=("Arial", 12),
            bg=self.accent_color,
            fg="#ffffff",
            activebackground="#45a049",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=5,
            command=self._submit
        )
        send_btn.pack(side=tk.RIGHT)
        
        # Position window
        self.root.update_idletasks()
        
        if x is None or y is None:
            x = self.root.winfo_pointerx()
            y = self.root.winfo_pointery() + 20
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = self.root.winfo_reqwidth()
        window_height = self.root.winfo_reqheight()
        
        if x + window_width > screen_width:
            x = screen_width - window_width - 10
        if y + window_height > screen_height:
            y = y - window_height - 30
        
        self.root.geometry(f"+{x}+{y}")
        self.root.deiconify()
        
        self.root.bind('<Escape>', lambda e: self._close())
        
        # Focus the window
        self.root.lift()
        self.root.focus_force()
        input_entry.focus_set()
        
        self.root.mainloop()
    
    def _submit(self):
        """Handle submit."""
        text = self.input_var.get().strip()
        if text and text != "Ask your AI...":
            self._close()
            self.on_submit(text)
    
    def _close(self):
        super()._close()
        if self.on_close_callback:
            self.on_close_callback()


class PromptSelectionPopup(BasePopup):
    """
    Popup with prompt selection buttons for when text is selected.
    Shows input field plus predefined prompt options.
    """
    
    def __init__(
        self,
        options: Dict,
        on_option_selected: Callable[[str, str, Optional[str]], None],
        on_close: Optional[Callable[[], None]] = None
    ):
        super().__init__()
        self.options = options
        self.on_option_selected = on_option_selected
        self.on_close_callback = on_close
        self.selected_text = ""
        self.input_var: Optional[tk.StringVar] = None
        self.response_mode_var: Optional[tk.StringVar] = None  # "default", "replace", "show"
    
    def show(self, selected_text: str, x: Optional[int] = None, y: Optional[int] = None):
        """Show the popup window."""
        self.selected_text = selected_text
        
        self.root = tk.Tk()
        self.root.withdraw()
        
        self.root.title("Text Edit Tool")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg=self.bg_color)
        
        # Main frame with border
        main_frame = tk.Frame(
            self.root,
            bg=self.bg_color,
            highlightbackground=self.border_color,
            highlightthickness=1
        )
        main_frame.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        
        content_frame = tk.Frame(main_frame, bg=self.bg_color)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Close button
        top_bar = tk.Frame(content_frame, bg=self.bg_color)
        top_bar.pack(fill=tk.X, pady=(0, 5))
        
        close_btn = tk.Button(
            top_bar,
            text="×",
            font=("Arial", 14, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            activebackground=self.button_hover,
            relief=tk.FLAT,
            bd=0,
            command=self._close
        )
        close_btn.pack(side=tk.RIGHT)
        
        # Response mode radio buttons
        mode_frame = tk.Frame(content_frame, bg=self.bg_color)
        mode_frame.pack(fill=tk.X, pady=(0, 8))
        
        tk.Label(
            mode_frame,
            text="Response:",
            font=("Arial", 9),
            bg=self.bg_color,
            fg=self.fg_color
        ).pack(side=tk.LEFT, padx=(0, 8))
        
        self.response_mode_var = tk.StringVar(value="default")
        
        for mode_text, mode_value in [("Default", "default"), ("Replace", "replace"), ("Show", "show")]:
            rb = tk.Radiobutton(
                mode_frame,
                text=mode_text,
                variable=self.response_mode_var,
                value=mode_value,
                font=("Arial", 9),
                bg=self.bg_color,
                fg=self.fg_color,
                selectcolor=self.input_bg,
                activebackground=self.bg_color,
                activeforeground=self.fg_color,
                highlightthickness=0
            )
            rb.pack(side=tk.LEFT, padx=2)
        
        # Input area
        input_frame = tk.Frame(content_frame, bg=self.bg_color)
        input_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.input_var = tk.StringVar()
        placeholder = "Describe your change..."
        
        input_entry = tk.Entry(
            input_frame,
            textvariable=self.input_var,
            font=("Arial", 11),
            bg=self.input_bg,
            fg=self.fg_color,
            insertbackground=self.fg_color,
            relief=tk.FLAT,
            highlightbackground=self.border_color,
            highlightthickness=1
        )
        input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5), ipady=8)
        input_entry.insert(0, placeholder)
        input_entry.config(fg='gray')
        
        def on_focus_in(event):
            if input_entry.get() == placeholder:
                input_entry.delete(0, tk.END)
                input_entry.config(fg=self.fg_color)
        
        def on_focus_out(event):
            if not input_entry.get():
                input_entry.insert(0, placeholder)
                input_entry.config(fg='gray')
        
        input_entry.bind('<FocusIn>', on_focus_in)
        input_entry.bind('<FocusOut>', on_focus_out)
        input_entry.bind('<Return>', lambda e: self._on_custom_submit())
        
        # Send button
        send_btn = tk.Button(
            input_frame,
            text="➤",
            font=("Arial", 12),
            bg=self.accent_color,
            fg="#ffffff",
            activebackground="#45a049",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=5,
            command=self._on_custom_submit
        )
        send_btn.pack(side=tk.RIGHT)
        
        # Option buttons in grid
        self._create_option_buttons(content_frame)
        
        # Position window
        self.root.update_idletasks()
        
        if x is None or y is None:
            x = self.root.winfo_pointerx()
            y = self.root.winfo_pointery() + 20
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = self.root.winfo_reqwidth()
        window_height = self.root.winfo_reqheight()
        
        if x + window_width > screen_width:
            x = screen_width - window_width - 10
        if y + window_height > screen_height:
            y = y - window_height - 30
        
        self.root.geometry(f"+{x}+{y}")
        self.root.deiconify()
        
        self.root.bind('<Escape>', lambda e: self._close())
        
        # Focus the window
        self.root.lift()
        self.root.focus_force()
        input_entry.focus_set()
        
        self.root.mainloop()
    
    def _create_option_buttons(self, parent: tk.Frame):
        """Create option buttons in a grid."""
        buttons_frame = tk.Frame(parent, bg=self.bg_color)
        buttons_frame.pack(fill=tk.BOTH, expand=True)
        
        row = 0
        col = 0
        
        for key, option in self.options.items():
            if key == "Custom":
                continue
            
            btn = tk.Button(
                buttons_frame,
                text=key,
                font=("Arial", 10),
                bg=self.button_bg,
                fg=self.fg_color,
                activebackground=self.button_hover,
                relief=tk.FLAT,
                bd=0,
                padx=15,
                pady=8,
                width=12,
                anchor=tk.W,
                command=lambda k=key: self._on_option_click(k)
            )
            btn.grid(row=row, column=col, padx=3, pady=3, sticky=tk.EW)
            
            btn.bind('<Enter>', lambda e, b=btn: b.config(bg=self.button_hover))
            btn.bind('<Leave>', lambda e, b=btn: b.config(bg=self.button_bg))
            
            col += 1
            if col > 1:
                col = 0
                row += 1
        
        buttons_frame.columnconfigure(0, weight=1)
        buttons_frame.columnconfigure(1, weight=1)
    
    def _on_option_click(self, option_key: str):
        """Handle option button click."""
        logging.debug(f'Option selected: {option_key}')
        response_mode = self.response_mode_var.get() if self.response_mode_var else "default"
        self._close()
        self.on_option_selected(option_key, self.selected_text, None, response_mode)
    
    def _on_custom_submit(self):
        """Handle custom input submission."""
        custom_text = self.input_var.get().strip()
        
        if not custom_text or custom_text == "Describe your change...":
            return
        
        logging.debug(f'Custom input submitted: {custom_text[:50]}...')
        response_mode = self.response_mode_var.get() if self.response_mode_var else "default"
        self._close()
        self.on_option_selected("Custom", self.selected_text, custom_text, response_mode)
    
    def _close(self):
        super()._close()
        if self.on_close_callback:
            self.on_close_callback()
