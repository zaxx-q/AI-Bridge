#!/usr/bin/env python3
"""
Tkinter-based popup window for prompt selection
"""

import logging
import os
import sys
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Dict, List
import json

try:
    import darkdetect
    HAVE_DARKDETECT = True
except ImportError:
    HAVE_DARKDETECT = False
    darkdetect = None


def is_dark_mode() -> bool:
    """Check if system is in dark mode."""
    if HAVE_DARKDETECT:
        try:
            return darkdetect.isDark()
        except Exception:
            pass
    return False


class PopupWindow:
    """
    Tkinter-based popup window for prompt selection.
    Shows near the cursor position.
    """
    
    def __init__(
        self,
        options: Dict,
        on_option_selected: Callable[[str, str, Optional[str]], None],
        on_close: Optional[Callable[[], None]] = None
    ):
        """
        Initialize the popup window.
        
        Args:
            options: Dictionary of option configurations
            on_option_selected: Callback when option is selected (option_key, selected_text, custom_input)
            on_close: Optional callback when window is closed
        """
        self.options = options
        self.on_option_selected = on_option_selected
        self.on_close = on_close
        self.root: Optional[tk.Tk] = None
        self.selected_text = ""
        self.custom_input_var: Optional[tk.StringVar] = None
        
        # Theme colors
        self.dark_mode = is_dark_mode()
        self._setup_colors()
        
        logging.debug('PopupWindow initialized')
    
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
    
    def show(self, selected_text: str = "", x: Optional[int] = None, y: Optional[int] = None):
        """
        Show the popup window.
        
        Args:
            selected_text: The currently selected text
            x: X position (uses cursor position if not provided)
            y: Y position (uses cursor position if not provided)
        """
        self.selected_text = selected_text
        has_text = bool(selected_text.strip())
        
        # Create root window
        self.root = tk.Tk()
        self.root.withdraw()  # Hide initially
        
        # Configure window
        self.root.title("Text Edit Tool")
        self.root.overrideredirect(True)  # Frameless
        self.root.attributes('-topmost', True)
        self.root.configure(bg=self.bg_color)
        
        # Create main frame with border
        main_frame = tk.Frame(
            self.root,
            bg=self.bg_color,
            highlightbackground=self.border_color,
            highlightthickness=1
        )
        main_frame.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        
        # Create content
        content_frame = tk.Frame(main_frame, bg=self.bg_color)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Top bar with close button
        top_bar = tk.Frame(content_frame, bg=self.bg_color)
        top_bar.pack(fill=tk.X, pady=(0, 5))
        
        close_btn = tk.Button(
            top_bar,
            text="×",
            font=("Arial", 14, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            activebackground=self.button_hover,
            activeforeground=self.fg_color,
            relief=tk.FLAT,
            bd=0,
            padx=5,
            pady=0,
            command=self._close
        )
        close_btn.pack(side=tk.RIGHT)
        
        # Input area
        input_frame = tk.Frame(content_frame, bg=self.bg_color)
        input_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.custom_input_var = tk.StringVar()
        
        placeholder = "Describe your change..." if has_text else "Ask your AI..."
        
        input_entry = tk.Entry(
            input_frame,
            textvariable=self.custom_input_var,
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
        
        # Placeholder behavior
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
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=5,
            command=self._on_custom_submit
        )
        send_btn.pack(side=tk.RIGHT)
        
        # Only show option buttons if text is selected
        if has_text:
            self._create_option_buttons(content_frame)
        else:
            # Make input wider when no text selected
            input_entry.config(width=40)
        
        # Update window to get size
        self.root.update_idletasks()
        
        # Position window
        if x is None or y is None:
            # Get cursor position
            x = self.root.winfo_pointerx()
            y = self.root.winfo_pointery() + 20  # 20px below cursor
        
        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = self.root.winfo_reqwidth()
        window_height = self.root.winfo_reqheight()
        
        # Adjust if window would go off screen
        if x + window_width > screen_width:
            x = screen_width - window_width - 10
        if y + window_height > screen_height:
            y = y - window_height - 30  # Above cursor
        
        self.root.geometry(f"+{x}+{y}")
        
        # Show window
        self.root.deiconify()
        
        # Focus on input
        input_entry.focus_set()
        if input_entry.get() == placeholder:
            input_entry.selection_range(0, tk.END)
        
        # Bind events
        self.root.bind('<Escape>', lambda e: self._close())
        self.root.bind('<FocusOut>', self._on_focus_out)
        
        # Start main loop
        self.root.mainloop()
    
    def _create_option_buttons(self, parent: tk.Frame):
        """Create option buttons in a grid."""
        buttons_frame = tk.Frame(parent, bg=self.bg_color)
        buttons_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create buttons in a grid (2 columns)
        row = 0
        col = 0
        
        for key, option in self.options.items():
            if key == "Custom":
                continue  # Custom is handled by the input field
            
            btn = tk.Button(
                buttons_frame,
                text=key,
                font=("Arial", 10),
                bg=self.button_bg,
                fg=self.fg_color,
                activebackground=self.button_hover,
                activeforeground=self.fg_color,
                relief=tk.FLAT,
                bd=0,
                padx=15,
                pady=8,
                width=12,
                anchor=tk.W,
                command=lambda k=key: self._on_option_click(k)
            )
            btn.grid(row=row, column=col, padx=3, pady=3, sticky=tk.EW)
            
            # Hover effect
            btn.bind('<Enter>', lambda e, b=btn: b.config(bg=self.button_hover))
            btn.bind('<Leave>', lambda e, b=btn: b.config(bg=self.button_bg))
            
            col += 1
            if col > 1:
                col = 0
                row += 1
        
        # Configure grid columns to expand equally
        buttons_frame.columnconfigure(0, weight=1)
        buttons_frame.columnconfigure(1, weight=1)
    
    def _on_option_click(self, option_key: str):
        """Handle option button click."""
        logging.debug(f'Option selected: {option_key}')
        self._close()
        self.on_option_selected(option_key, self.selected_text, None)
    
    def _on_custom_submit(self):
        """Handle custom input submission."""
        custom_text = self.custom_input_var.get().strip()
        
        # Ignore placeholder text
        placeholders = ["Describe your change...", "Ask your AI..."]
        if not custom_text or custom_text in placeholders:
            return
        
        logging.debug(f'Custom input submitted: {custom_text[:50]}...')
        self._close()
        self.on_option_selected("Custom", self.selected_text, custom_text)
    
    def _on_focus_out(self, event):
        """Handle focus out event - close if clicking outside."""
        # Only close if focus went outside the window entirely
        if self.root and event.widget == self.root:
            # Small delay to check if focus is still in a child widget
            self.root.after(100, self._check_focus)
    
    def _check_focus(self):
        """Check if focus is still in the window."""
        if not self.root:
            return
        
        try:
            focused = self.root.focus_get()
            if focused is None:
                self._close()
        except Exception:
            pass
    
    def _close(self):
        """Close the popup window."""
        if self.root:
            self.root.destroy()
            self.root = None
        
        if self.on_close:
            self.on_close()
    
    def is_open(self) -> bool:
        """Check if the popup is currently open."""
        return self.root is not None and self.root.winfo_exists()


def show_popup(
    options: Dict,
    selected_text: str,
    on_option_selected: Callable[[str, str, Optional[str]], None],
    on_close: Optional[Callable[[], None]] = None
):
    """
    Convenience function to show a popup window.
    
    Args:
        options: Dictionary of option configurations
        selected_text: Currently selected text
        on_option_selected: Callback when option is selected
        on_close: Optional callback when window is closed
    """
    popup = PopupWindow(
        options=options,
        on_option_selected=on_option_selected,
        on_close=on_close
    )
    popup.show(selected_text)
