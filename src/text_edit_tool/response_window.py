#!/usr/bin/env python3
"""
Tkinter-based response window for displaying AI responses with follow-up support
"""

import logging
import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Callable, Optional, List, Dict
import threading

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


class ResponseWindow:
    """
    Tkinter-based response window for displaying AI responses.
    Supports follow-up questions and chat history.
    """
    
    def __init__(
        self,
        title: str = "AI Response",
        on_followup: Optional[Callable[[str, List[Dict]], None]] = None,
        on_close: Optional[Callable[[], None]] = None
    ):
        """
        Initialize the response window.
        
        Args:
            title: Window title
            on_followup: Callback for follow-up questions (question, chat_history)
            on_close: Callback when window is closed
        """
        self.title = title
        self.on_followup = on_followup
        self.on_close = on_close
        self.root: Optional[tk.Tk] = None
        self.response_text: Optional[scrolledtext.ScrolledText] = None
        self.input_entry: Optional[tk.Entry] = None
        self.input_var: Optional[tk.StringVar] = None
        self.send_btn: Optional[tk.Button] = None
        self.thinking_label: Optional[tk.Label] = None
        
        self.chat_history: List[Dict[str, str]] = []
        self.is_loading = False
        self.thinking_dots = 0
        self.thinking_timer = None
        
        # Theme colors
        self.dark_mode = is_dark_mode()
        self._setup_colors()
        
        logging.debug('ResponseWindow initialized')
    
    def _setup_colors(self):
        """Setup color scheme based on dark/light mode."""
        if self.dark_mode:
            self.bg_color = "#1e1e1e"
            self.fg_color = "#ffffff"
            self.text_bg = "#2d2d2d"
            self.input_bg = "#333333"
            self.border_color = "#555555"
            self.accent_color = "#4CAF50"
            self.user_msg_bg = "#3d3d3d"
            self.ai_msg_bg = "#2d2d2d"
        else:
            self.bg_color = "#f5f5f5"
            self.fg_color = "#333333"
            self.text_bg = "#ffffff"
            self.input_bg = "#ffffff"
            self.border_color = "#cccccc"
            self.accent_color = "#4CAF50"
            self.user_msg_bg = "#e8f5e9"
            self.ai_msg_bg = "#ffffff"
    
    def show(self, initial_response: str = "", selected_text: str = ""):
        """
        Show the response window.
        
        Args:
            initial_response: Initial AI response to display
            selected_text: The original selected text (for context)
        """
        # Create root window
        self.root = tk.Tk()
        self.root.title(self.title)
        self.root.geometry("600x500")
        self.root.configure(bg=self.bg_color)
        self.root.minsize(400, 300)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        
        # Top bar
        top_bar = tk.Frame(self.root, bg=self.bg_color)
        top_bar.grid(row=0, column=0, sticky=tk.EW, padx=15, pady=(10, 5))
        
        title_label = tk.Label(
            top_bar,
            text=self.title,
            font=("Arial", 14, "bold"),
            bg=self.bg_color,
            fg=self.fg_color
        )
        title_label.pack(side=tk.LEFT)
        
        # Copy button
        copy_btn = tk.Button(
            top_bar,
            text="Copy",
            font=("Arial", 9),
            bg=self.input_bg,
            fg=self.fg_color,
            activebackground=self.border_color,
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=3,
            command=self._copy_response
        )
        copy_btn.pack(side=tk.RIGHT)
        
        # Response area
        text_frame = tk.Frame(self.root, bg=self.bg_color)
        text_frame.grid(row=1, column=0, sticky=tk.NSEW, padx=15, pady=5)
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        
        self.response_text = scrolledtext.ScrolledText(
            text_frame,
            wrap=tk.WORD,
            font=("Arial", 11),
            bg=self.text_bg,
            fg=self.fg_color,
            insertbackground=self.fg_color,
            relief=tk.FLAT,
            highlightbackground=self.border_color,
            highlightthickness=1,
            padx=10,
            pady=10
        )
        self.response_text.grid(row=0, column=0, sticky=tk.NSEW)
        
        # Configure text tags for styling
        self.response_text.tag_configure("user", background=self.user_msg_bg, lmargin1=10, lmargin2=10)
        self.response_text.tag_configure("ai", background=self.ai_msg_bg, lmargin1=10, lmargin2=10)
        self.response_text.tag_configure("bold", font=("Arial", 11, "bold"))
        self.response_text.tag_configure("italic", font=("Arial", 11, "italic"))
        self.response_text.tag_configure("code", font=("Consolas", 10), background="#1e1e1e" if self.dark_mode else "#f0f0f0")
        
        # Thinking label (hidden initially)
        self.thinking_label = tk.Label(
            self.root,
            text="Thinking...",
            font=("Arial", 11),
            bg=self.bg_color,
            fg=self.fg_color
        )
        
        # Input area
        input_frame = tk.Frame(self.root, bg=self.bg_color)
        input_frame.grid(row=2, column=0, sticky=tk.EW, padx=15, pady=(5, 15))
        input_frame.columnconfigure(0, weight=1)
        
        self.input_var = tk.StringVar()
        self.input_entry = tk.Entry(
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
        self.input_entry.grid(row=0, column=0, sticky=tk.EW, ipady=8, padx=(0, 5))
        self.input_entry.insert(0, "Ask a follow-up question...")
        self.input_entry.config(fg='gray')
        
        # Placeholder behavior
        def on_focus_in(event):
            if self.input_entry.get() == "Ask a follow-up question...":
                self.input_entry.delete(0, tk.END)
                self.input_entry.config(fg=self.fg_color)
        
        def on_focus_out(event):
            if not self.input_entry.get():
                self.input_entry.insert(0, "Ask a follow-up question...")
                self.input_entry.config(fg='gray')
        
        self.input_entry.bind('<FocusIn>', on_focus_in)
        self.input_entry.bind('<FocusOut>', on_focus_out)
        self.input_entry.bind('<Return>', lambda e: self._send_followup())
        
        # Send button
        self.send_btn = tk.Button(
            input_frame,
            text="➤",
            font=("Arial", 12),
            bg=self.accent_color,
            fg="#ffffff",
            activebackground="#45a049",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=5,
            command=self._send_followup
        )
        self.send_btn.grid(row=0, column=1)
        
        # Initialize with response
        if initial_response:
            self._add_message(initial_response, is_user=False)
            
            # Add to chat history
            if selected_text.strip():
                self.chat_history.append({
                    "role": "user",
                    "content": f"Original text:\n\n{selected_text}"
                })
            self.chat_history.append({
                "role": "assistant",
                "content": initial_response
            })
        
        # Bind close event
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Start main loop
        self.root.mainloop()
    
    def _add_message(self, text: str, is_user: bool = False):
        """Add a message to the response area."""
        if not self.response_text:
            return
        
        self.response_text.config(state=tk.NORMAL)
        
        # Add some spacing between messages
        if self.response_text.get("1.0", tk.END).strip():
            self.response_text.insert(tk.END, "\n\n")
        
        # Add prefix
        if is_user:
            self.response_text.insert(tk.END, "You: ", "bold")
        else:
            self.response_text.insert(tk.END, "AI: ", "bold")
        
        # Add message text
        tag = "user" if is_user else "ai"
        self.response_text.insert(tk.END, text, tag)
        
        self.response_text.config(state=tk.DISABLED)
        
        # Scroll to bottom
        self.response_text.see(tk.END)
    
    def _send_followup(self):
        """Send a follow-up question."""
        if self.is_loading or not self.input_entry:
            return
        
        question = self.input_var.get().strip()
        
        # Ignore placeholder
        if not question or question == "Ask a follow-up question...":
            return
        
        # Clear input
        self.input_var.set("")
        
        # Add user message
        self._add_message(question, is_user=True)
        self.chat_history.append({
            "role": "user",
            "content": question
        })
        
        # Start loading state
        self._set_loading(True)
        
        # Call callback
        if self.on_followup:
            self.on_followup(question, self.chat_history.copy())
    
    def add_response(self, response: str):
        """
        Add an AI response (called from main thread).
        
        Args:
            response: The AI response text
        """
        if self.root:
            self.root.after(0, lambda: self._add_response_internal(response))
    
    def _add_response_internal(self, response: str):
        """Internal method to add response (runs in main thread)."""
        self._set_loading(False)
        self._add_message(response, is_user=False)
        self.chat_history.append({
            "role": "assistant",
            "content": response
        })
    
    def show_error(self, error: str):
        """
        Show an error message.
        
        Args:
            error: Error message
        """
        if self.root:
            self.root.after(0, lambda: self._show_error_internal(error))
    
    def _show_error_internal(self, error: str):
        """Internal method to show error."""
        self._set_loading(False)
        self._add_message(f"Error: {error}", is_user=False)
    
    def _set_loading(self, loading: bool):
        """Set loading state."""
        self.is_loading = loading
        
        if loading:
            # Disable input
            if self.input_entry:
                self.input_entry.config(state=tk.DISABLED)
            if self.send_btn:
                self.send_btn.config(state=tk.DISABLED)
            
            # Show thinking label
            if self.thinking_label:
                self.thinking_label.grid(row=1, column=0, sticky=tk.S, pady=10)
                self._start_thinking_animation()
        else:
            # Enable input
            if self.input_entry:
                self.input_entry.config(state=tk.NORMAL)
            if self.send_btn:
                self.send_btn.config(state=tk.NORMAL)
            
            # Hide thinking label
            if self.thinking_label:
                self.thinking_label.grid_remove()
            self._stop_thinking_animation()
    
    def _start_thinking_animation(self):
        """Start the thinking dots animation."""
        self.thinking_dots = 0
        self._update_thinking_dots()
    
    def _update_thinking_dots(self):
        """Update thinking dots animation."""
        if not self.is_loading or not self.thinking_label:
            return
        
        dots = "." * (self.thinking_dots % 4)
        self.thinking_label.config(text=f"Thinking{dots}")
        self.thinking_dots += 1
        
        self.thinking_timer = self.root.after(300, self._update_thinking_dots)
    
    def _stop_thinking_animation(self):
        """Stop the thinking animation."""
        if self.thinking_timer and self.root:
            self.root.after_cancel(self.thinking_timer)
            self.thinking_timer = None
    
    def _copy_response(self):
        """Copy the response text to clipboard."""
        if not self.response_text:
            return
        
        # Get all text
        text = self.response_text.get("1.0", tk.END).strip()
        
        # Copy to clipboard
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
    
    def _on_close(self):
        """Handle window close."""
        self._stop_thinking_animation()
        
        if self.root:
            self.root.destroy()
            self.root = None
        
        if self.on_close:
            self.on_close()
    
    def is_open(self) -> bool:
        """Check if the window is currently open."""
        return self.root is not None
    
    def focus(self):
        """Bring window to focus."""
        if self.root:
            self.root.lift()
            self.root.focus_force()
