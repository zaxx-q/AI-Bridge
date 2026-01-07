#!/usr/bin/env python3
"""
GUI window creation functions - CustomTkinter implementation

Threading Note:
    CustomTkinter is not thread-safe. Only ONE CTk() instance should have mainloop() running
    at a time. To avoid conflicts, standalone windows use a polling loop (update + sleep)
    instead of blocking mainloop(). This allows multiple windows to coexist in different
    threads without blocking each other.

CustomTkinter Migration Notes:
    - Uses CTk()/CTkToplevel for modern appearance with rounded corners
    - CTkButton, CTkFrame, CTkLabel for consistent theming
    - Hybrid approach: tk.Text kept for chat display (tag-based markdown rendering)
    - CTkScrollbar for themed scrollbars
    - CTkComboBox replaces ttk.Combobox
    - Custom scrollable frame replaces ttk.Treeview for session list
"""

import os
import sys
import threading
import time
import tkinter as tk
from typing import Optional, Dict, List

# Import CustomTkinter with fallback
try:
    import customtkinter as ctk
    HAVE_CTK = True
except ImportError:
    HAVE_CTK = False
    ctk = None

from ..utils import strip_markdown
from ..session_manager import add_session, get_session, list_sessions, delete_session, save_sessions, ChatSession
from .core import get_next_window_id, register_window, unregister_window
from .utils import copy_to_clipboard, render_markdown, get_color_scheme, setup_text_tags
from .custom_widgets import create_emoji_button
from .themes import (
    ThemeColors, get_colors, get_ctk_font,
    get_ctk_button_colors, get_ctk_frame_colors,
    get_ctk_entry_colors, get_ctk_textbox_colors, get_ctk_scrollbar_colors,
    get_ctk_combobox_colors, apply_hover_effect, sync_ctk_appearance
)

# Import emoji renderer for CTkImage support (Windows color emoji fix)
try:
    from .emoji_renderer import get_emoji_renderer, HAVE_PIL
    HAVE_EMOJI = HAVE_PIL and HAVE_CTK
except ImportError:
    HAVE_EMOJI = False
    get_emoji_renderer = None


def get_icon_path():
    """Get the path to the application icon."""
    # Handle frozen state (executable)
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
        icon_path = os.path.join(base_dir, "icon.ico")
        if os.path.exists(icon_path):
            return icon_path
            
    # Development mode
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    icon_path = os.path.join(base_dir, "icon.ico")
    if os.path.exists(icon_path):
        return icon_path
    return None


def set_window_icon(window, delay_ms: int = 100):
    """
    Set the window icon to the AI-Bridge icon.
    
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


# =============================================================================
# Session List Components (lightweight tk-based for performance)
# =============================================================================

class SessionListItem(tk.Frame):
    """
    A single session row in the session browser list.
    Uses lightweight tk widgets with grid layout for proper alignment (fixing font width issues).
    """
    
    def __init__(self, parent, session_data: Dict, colors: ThemeColors,
                 on_click, on_double_click, **kwargs):
        # Remove CTk-specific kwargs if present
        kwargs.pop('fg_color', None)
        kwargs.pop('corner_radius', None)
        
        super().__init__(
            parent,
            bg=colors.surface0,
            height=36,
            **kwargs
        )
        self.session_data = session_data
        self.colors = colors
        self.on_click_callback = on_click
        self.on_double_click_callback = on_double_click
        self.selected = False
        
        # Use grid layout for column alignment (pixel-perfect)
        # MUST match SessionListHeader grid config
        self.grid_columnconfigure(0, minsize=60)   # ID
        self.grid_columnconfigure(1, weight=1)     # Title
        self.grid_columnconfigure(2, minsize=100)  # Endpoint
        self.grid_columnconfigure(3, minsize=70)   # Msgs
        self.grid_columnconfigure(4, minsize=140)  # Updated
        
        self.pack_propagate(False)
        self.grid_propagate(False)
        
        # Data preparation
        sid = str(session_data.get('id', ''))
        title = session_data.get('title', '') or 'Untitled'
        # Truncate very long titles for display
        if len(title) > 60:
            title = title[:60] + '...'
            
        endpoint = session_data.get('endpoint', '')
        msgs = str(session_data.get('messages', 0))
        updated = session_data.get('updated', '')
        if updated:
            updated = updated[:16].replace('T', ' ')
        
        font = ("Segoe UI", 10)
        self.cells = []
        
        # Helper to create cells
        def create_cell(text, col, anchor="w", sticky="w"):
            lbl = tk.Label(
                self,
                text=text,
                font=font,
                bg=colors.surface0,
                fg=colors.fg,
                anchor=anchor,
                padx=5,
                pady=8,
                cursor="hand2"
            )
            lbl.grid(row=0, column=col, sticky=sticky, padx=(10 if col==0 else 0, 0))
            self.cells.append(lbl)
            
            # Event binding
            lbl.bind("<Button-1>", lambda e: self._on_click())
            lbl.bind("<Double-1>", lambda e: self._on_double_click())
            lbl.bind("<Enter>", lambda e: self._on_hover(True))
            lbl.bind("<Leave>", lambda e: self._on_hover(False))

        # Create columns
        create_cell(sid, 0, "w", "ew")
        create_cell(title, 1, "w", "ew")
        create_cell(endpoint, 2, "w", "ew")
        create_cell(msgs, 3, "center", "ew")
        create_cell(updated, 4, "w", "ew")

        # Bind events to the frame itself too
        self.bind("<Button-1>", lambda e: self._on_click())
        self.bind("<Double-1>", lambda e: self._on_double_click())
        self.bind("<Enter>", lambda e: self._on_hover(True))
        self.bind("<Leave>", lambda e: self._on_hover(False))

    def _on_click(self):
        """Handle single click."""
        if self.on_click_callback:
            self.on_click_callback(self.session_data)
    
    def _on_double_click(self):
        """Handle double click."""
        if self.on_double_click_callback:
            self.on_double_click_callback(self.session_data)
    
    def _on_hover(self, entering: bool):
        """Handle hover effect."""
        if self.selected:
            return
        
        color = self.colors.surface1 if entering else self.colors.surface0
        self.configure(bg=color)
        for cell in self.cells:
            cell.configure(bg=color)
    
    def set_selected(self, selected: bool):
        """Set selection state."""
        self.selected = selected
        
        if selected:
            bg = self.colors.accent
            fg = "#ffffff"
        else:
            bg = self.colors.surface0
            fg = self.colors.fg
        
        self.configure(bg=bg)
        for cell in self.cells:
            cell.configure(bg=bg, fg=fg)


class SessionListHeader(tk.Frame):
    """
    Column headers for session list with click-to-sort functionality.
    Uses grid layout with fixed columns for alignment.
    """
    
    def __init__(self, parent, colors: ThemeColors, on_sort, current_sort, descending, **kwargs):
        # Remove CTk-specific kwargs
        kwargs.pop('fg_color', None)
        kwargs.pop('corner_radius', None)
        
        super().__init__(
            parent,
            bg=colors.surface1,
            height=30,
            **kwargs
        )
        self.colors = colors
        self.on_sort = on_sort
        self.current_sort = current_sort
        self.descending = descending
        
        # Grid config (Must match SessionListItem)
        self.grid_columnconfigure(0, minsize=60)   # ID
        self.grid_columnconfigure(1, weight=1)     # Title
        self.grid_columnconfigure(2, minsize=100)  # Endpoint
        self.grid_columnconfigure(3, minsize=70)   # Msgs
        self.grid_columnconfigure(4, minsize=140)  # Updated
        
        self.pack_propagate(False)
        self.grid_propagate(False)
        
        self.cells = {}
        self._create_headers()
        
    def _create_headers(self):
        font = ("Segoe UI", 10, "bold")
        
        def create_header(text, col, sort_key, anchor="w", sticky="w"):
            # Determine indicator
            indicator = ""
            actual_sort_key = "Messages" if sort_key == "Msgs" else sort_key
            
            if self.current_sort == actual_sort_key:
                indicator = " ▼" if self.descending else " ▲"
            
            lbl = tk.Label(
                self,
                text=text + indicator,
                font=font,
                bg=self.colors.surface1,
                fg=self.colors.fg,
                anchor=anchor,
                padx=5,
                pady=6,
                cursor="hand2"
            )
            lbl.grid(row=0, column=col, sticky=sticky, padx=(10 if col==0 else 0, 0))
            
            lbl.bind("<Button-1>", lambda e: self.on_sort(actual_sort_key) if self.on_sort else None)
            self.cells[actual_sort_key] = lbl
        
        create_header("ID", 0, "ID", "w", "ew")
        create_header("Title", 1, "Title", "w", "ew")
        create_header("Endpoint", 2, "Endpoint", "w", "ew")
        create_header("Msgs", 3, "Msgs", "center", "ew")
        create_header("Updated", 4, "Updated", "w", "ew")

    def update_sort_indicators(self, current_sort: str, descending: bool):
        """Update sort indicators on headers."""
        self.current_sort = current_sort
        self.descending = descending
        
        display_map = {
            "ID": "ID",
            "Title": "Title",
            "Endpoint": "Endpoint",
            "Messages": "Msgs",
            "Updated": "Updated"
        }
        
        for key, lbl in self.cells.items():
            base_text = display_map.get(key, key)
            if key == current_sort:
                indicator = " ▼" if descending else " ▲"
            else:
                indicator = ""
            lbl.configure(text=base_text + indicator)


# =============================================================================
# Standalone Chat Window
# =============================================================================

class StandaloneChatWindow:
    """
    Standalone chat window that creates its own CTk root.
    Used when launching from non-GUI contexts.
    """
    
    def __init__(self, session, initial_response: Optional[str] = None):
        self.session = session
        self.initial_response = initial_response
        
        self.window_id = get_next_window_id()
        self.window_tag = f"standalone_chat_{self.window_id}"
        
        # State
        self.wrapped = True
        self.markdown = True
        self.auto_scroll = True
        self.last_response = initial_response or ""
        self.is_loading = False
        self._destroyed = False
        
        # Streaming state
        self.streaming_text = ""
        self.streaming_thinking = ""
        self.is_streaming = False
        self.thinking_collapsed = True
        self.last_usage = None
        
        # Available models cache
        self.available_models = []
        from .. import web_server
        provider = web_server.CONFIG.get("default_provider", "google")
        self.selected_model = web_server.CONFIG.get(f"{provider}_model", "")
        
        # Colors - get ThemeColors object
        self.theme = get_colors()
        self.colors = get_color_scheme()  # Dict for compatibility
        
        self.root = None
    
    def _safe_after(self, delay: int, func):
        """Schedule a callback only if window still exists."""
        if self._destroyed:
            return
        try:
            if self.root and self.root.winfo_exists():
                self.root.after(delay, func)
        except Exception:
            pass
    
    def show(self):
        """Create and show the window with its own mainloop"""
        # Sync appearance mode
        if HAVE_CTK:
            sync_ctk_appearance()
            self.root = ctk.CTk()
        else:
            self.root = tk.Tk()
        
        # Hide window while building UI (prevents flashing)
        self.root.withdraw()
        
        self.root.title(f"Chat - {self.session.title or self.session.session_id}")
        self.root.geometry("750x620")
        self.root.minsize(500, 400)
        
        # Position window
        offset = (self.window_id % 5) * 30
        self.root.geometry(f"+{80 + offset}+{80 + offset}")
        
        # Configure grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        
        # Session info
        from .. import web_server
        current_provider = web_server.CONFIG.get("default_provider", "google")
        info_text = f"Session: {self.session.session_id} | Endpoint: /{self.session.endpoint} | Provider: {current_provider}"
        
        if HAVE_CTK:
            ctk.CTkLabel(
                self.root,
                text=info_text,
                font=get_ctk_font(size=11),
                text_color=self.theme.blockquote
            ).grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))
        else:
            tk.Label(
                self.root, text=info_text, font=("Segoe UI", 9),
                bg=self.colors["bg"], fg=self.colors["blockquote"]
            ).grid(row=0, column=0, sticky=tk.W, padx=15, pady=(10, 5))
        
        # Toggle buttons row
        self._create_toolbar()
        
        # Chat log area (hybrid: CTkFrame + tk.Text)
        self._create_chat_area()
        
        # Input section
        self._create_input_area()
        
        # Button row
        self._create_action_buttons()
        
        # Register and bind
        register_window(self.window_tag)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        
        # Initial display
        self._update_chat_display(scroll_to_bottom=True)
        
        # Force Tk to process all pending drawing commands before showing
        self.root.update_idletasks()
        
        # Show window after UI is fully rendered
        self.root.deiconify()
        
        # Set window icon AFTER deiconify (CTk overrides icon during setup)
        set_window_icon(self.root)
        
        # Focus - use after() for reliable focus
        self.root.after(50, lambda: self._focus_window())
        
        # Run event loop
        self._run_event_loop()
    
    def _focus_window(self):
        """Focus the window reliably."""
        if self._destroyed or not self.root:
            return
        try:
            self.root.lift()
            self.root.focus_force()
            self.root.attributes('-topmost', True)
            self.root.after(100, lambda: self.root.attributes('-topmost', False) if self.root else None)
        except tk.TclError:
            pass
    
    def _create_toolbar(self):
        """Create the toolbar with toggle buttons and model dropdown."""
        if HAVE_CTK:
            btn_frame = ctk.CTkFrame(self.root, fg_color="transparent")
            btn_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=5)
            
            ctk.CTkLabel(
                btn_frame,
                text="Conversation:",
                font=get_ctk_font(size=12, weight="bold"),
                text_color=self.theme.accent
            ).pack(side="left", padx=(0, 10))
            
            # Toggle buttons with modern styling
            btn_colors = get_ctk_button_colors(self.theme, "secondary")
            
            self.wrap_btn = ctk.CTkButton(
                btn_frame,
                text="Wrap: ON",
                font=get_ctk_font(size=11),
                width=85,
                height=28,
                corner_radius=6,
                command=self._toggle_wrap,
                **btn_colors
            )
            self.wrap_btn.pack(side="left", padx=2)
            
            self.md_btn = ctk.CTkButton(
                btn_frame,
                text="Markdown",
                font=get_ctk_font(size=11),
                width=85,
                height=28,
                corner_radius=6,
                command=self._toggle_markdown,
                **btn_colors
            )
            self.md_btn.pack(side="left", padx=2)
            
            self.scroll_btn = ctk.CTkButton(
                btn_frame,
                text="Autoscroll: ON",
                font=get_ctk_font(size=11),
                width=100,
                height=28,
                corner_radius=6,
                command=self._toggle_autoscroll,
                **btn_colors
            )
            self.scroll_btn.pack(side="left", padx=2)
            
            # Model dropdown
            ctk.CTkLabel(
                btn_frame,
                text="Model:",
                font=get_ctk_font(size=11),
                text_color=self.theme.fg
            ).pack(side="left", padx=(15, 5))
            
            combo_colors = get_ctk_combobox_colors(self.theme)
            self.model_dropdown = ctk.CTkComboBox(
                btn_frame,
                values=["(loading...)"],
                width=220,
                height=28,
                corner_radius=6,
                command=self._on_model_select,
                **combo_colors
            )
            self.model_dropdown.pack(side="left", padx=5)
            self.model_dropdown.set(self.selected_model or "(default)")
            
            # Load models in background
            threading.Thread(target=self._load_models, daemon=True).start()
        else:
            # Fallback to tk
            btn_frame = tk.Frame(self.root, bg=self.colors["bg"])
            btn_frame.grid(row=1, column=0, sticky=tk.EW, padx=15, pady=5)
            # ... tk implementation (kept for fallback)
    
    def _create_chat_area(self):
        """Create the chat display area (hybrid: CTkFrame + tk.Text for markdown)."""
        if HAVE_CTK:
            chat_frame = ctk.CTkFrame(
                self.root,
                corner_radius=10,
                fg_color=self.theme.text_bg,
                border_color=self.theme.border,
                border_width=1
            )
            chat_frame.grid(row=2, column=0, sticky="nsew", padx=15, pady=5)
            chat_frame.columnconfigure(0, weight=1)
            chat_frame.rowconfigure(0, weight=1)
            
            # tk.Text for markdown rendering (tags not supported in CTkTextbox)
            self.chat_text = tk.Text(
                chat_frame,
                wrap=tk.WORD,
                font=("Segoe UI", 11),
                bg=self.theme.text_bg,
                fg=self.theme.fg,
                insertbackground=self.theme.fg,
                relief=tk.FLAT,
                highlightthickness=0,
                padx=12,
                pady=12,
                borderwidth=0
            )
            self.chat_text.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
            
            # CTkScrollbar for themed look
            scrollbar_colors = get_ctk_scrollbar_colors(self.theme)
            self.v_scrollbar = ctk.CTkScrollbar(
                chat_frame,
                command=self.chat_text.yview,
                corner_radius=4,
                width=14,
                **scrollbar_colors
            )
            self.v_scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=8)
            self.chat_text.configure(yscrollcommand=self.v_scrollbar.set)
            
            # Horizontal scrollbar (shown when wrap is off)
            self.h_scrollbar = ctk.CTkScrollbar(
                chat_frame,
                orientation="horizontal",
                command=self.chat_text.xview,
                corner_radius=4,
                height=14,
                **scrollbar_colors
            )
            self.h_scrollbar.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
            self.h_scrollbar.grid_remove()  # Hide initially
            self.chat_text.configure(xscrollcommand=self.h_scrollbar.set)
            
            # Setup text tags for markdown
            setup_text_tags(self.chat_text, self.colors)
            self.chat_text.tag_bind("thinking_header", "<Button-1>", self._on_thinking_click)
        else:
            # Fallback
            chat_frame = tk.Frame(self.root, bg=self.colors["bg"])
            chat_frame.grid(row=2, column=0, sticky=tk.NSEW, padx=15, pady=5)
            # ... tk implementation
    
    def _create_input_area(self):
        """Create the message input area."""
        if HAVE_CTK:
            ctk.CTkLabel(
                self.root,
                text="Your message:",
                font=get_ctk_font(size=12, weight="bold"),
                text_color=self.theme.accent
            ).grid(row=3, column=0, sticky="w", padx=15, pady=(10, 5))
            
            input_frame = ctk.CTkFrame(self.root, fg_color="transparent")
            input_frame.grid(row=4, column=0, sticky="ew", padx=15, pady=5)
            input_frame.columnconfigure(0, weight=1)
            
            # Use textbox colors (no placeholder_text_color - not supported by CTkTextbox)
            textbox_colors = get_ctk_textbox_colors(self.theme)
            self.input_text = ctk.CTkTextbox(
                input_frame,
                height=75,
                font=get_ctk_font(size=12),
                corner_radius=8,
                border_width=1,
                wrap="word",
                **textbox_colors
            )
            self.input_text.grid(row=0, column=0, sticky="ew")
            
            # Placeholder
            placeholder = "Type your follow-up message here... (Ctrl+Enter to send)"
            self.input_text.insert("0.0", placeholder)
            self.input_text.configure(text_color=self.theme.overlay0)
            
            def on_focus_in(event):
                content = self.input_text.get("0.0", "end-1c")
                if content == placeholder:
                    self.input_text.delete("0.0", "end")
                    self.input_text.configure(text_color=self.theme.fg)
            
            def on_focus_out(event):
                content = self.input_text.get("0.0", "end-1c").strip()
                if not content:
                    self.input_text.insert("0.0", placeholder)
                    self.input_text.configure(text_color=self.theme.overlay0)
            
            self.input_text.bind('<FocusIn>', on_focus_in)
            self.input_text.bind('<FocusOut>', on_focus_out)
            self.input_text.bind('<Control-Return>', lambda e: self._send())
        else:
            # Fallback
            input_frame = tk.Frame(self.root, bg=self.colors["bg"])
            input_frame.grid(row=4, column=0, sticky=tk.EW, padx=15, pady=5)
    
    def _create_action_buttons(self):
        """Create the action button row."""
        if HAVE_CTK:
            btn_row = ctk.CTkFrame(self.root, fg_color="transparent")
            btn_row.grid(row=5, column=0, sticky="ew", padx=15, pady=(5, 15))
            
            # Send button (success variant)
            send_colors = get_ctk_button_colors(self.theme, "success")
            self.send_btn = ctk.CTkButton(
                btn_row,
                text="Send",
                font=get_ctk_font(size=12, weight="bold"),
                width=80,
                height=32,
                corner_radius=8,
                command=self._send,
                **send_colors
            )
            self.send_btn.pack(side="left", padx=2)
            
            # Secondary buttons
            sec_colors = get_ctk_button_colors(self.theme, "secondary")
            
            ctk.CTkButton(
                btn_row,
                text="Copy All",
                font=get_ctk_font(size=12),
                width=85,
                height=32,
                corner_radius=8,
                command=self._copy_all,
                **sec_colors
            ).pack(side="left", padx=2)
            
            ctk.CTkButton(
                btn_row,
                text="Copy Last",
                font=get_ctk_font(size=12),
                width=85,
                height=32,
                corner_radius=8,
                command=self._copy_last,
                **sec_colors
            ).pack(side="left", padx=2)
            
            ctk.CTkButton(
                btn_row,
                text="Close",
                font=get_ctk_font(size=12),
                width=70,
                height=32,
                corner_radius=8,
                command=self._close,
                **sec_colors
            ).pack(side="left", padx=2)
            
            # Status label
            self.status_label = ctk.CTkLabel(
                btn_row,
                text="",
                font=get_ctk_font(size=11),
                text_color=self.theme.accent_green
            )
            self.status_label.pack(side="left", padx=15)
        else:
            # Fallback
            btn_row = tk.Frame(self.root, bg=self.colors["bg"])
            btn_row.grid(row=5, column=0, sticky=tk.EW, padx=15, pady=(5, 15))
    
    def _run_event_loop(self):
        """Run event loop without blocking other Tk instances."""
        try:
            while self.root is not None and not self._destroyed:
                try:
                    if not self.root.winfo_exists():
                        break
                    self.root.update()
                    time.sleep(0.01)
                except tk.TclError:
                    break
        except Exception:
            pass
    
    def _update_chat_display(self, scroll_to_bottom: bool = False, preserve_scroll: bool = False):
        """Update the chat display."""
        saved_scroll = None
        if preserve_scroll:
            saved_scroll = self.chat_text.yview()
        
        self.chat_text.configure(state=tk.NORMAL)
        self.chat_text.delete("1.0", tk.END)
        
        # Update button labels
        if HAVE_CTK:
            self.wrap_btn.configure(text=f"Wrap: {'ON' if self.wrapped else 'OFF'}")
            self.md_btn.configure(text="Markdown" if self.markdown else "Raw Text")
            self.scroll_btn.configure(text=f"Autoscroll: {'ON' if self.auto_scroll else 'OFF'}")
        
        # Render messages
        for i, msg in enumerate(self.session.messages):
            role = msg["role"]
            content = msg["content"]
            thinking = msg.get("thinking", "")
            
            if i > 0:
                self.chat_text.insert(tk.END, "\n")
            
            if role == "user":
                self.chat_text.insert(tk.END, "You:\n", "user_label")
            else:
                self.chat_text.insert(tk.END, "Assistant:\n", "assistant_label")
            
            if role == "assistant" and thinking:
                thinking_header = "▶ Thinking (click to expand)..." if self.thinking_collapsed else "▼ Thinking:"
                self.chat_text.insert(tk.END, f"{thinking_header}\n", "thinking_header")
                if not self.thinking_collapsed:
                    self.chat_text.insert(tk.END, thinking + "\n\n", "thinking_content")
            
            if self.markdown:
                role_for_bg = "user" if role == "user" else "assistant"
                render_markdown(content, self.chat_text, self.colors,
                              wrap=self.wrapped, as_role=role_for_bg)
            else:
                self.chat_text.configure(wrap=tk.WORD if self.wrapped else tk.NONE)
                self.chat_text.insert(tk.END, content, "normal")
            
            self.chat_text.insert(tk.END, "\n" + "─" * 50 + "\n", "separator")
        
        self.chat_text.configure(state=tk.DISABLED)
        
        if scroll_to_bottom and self.auto_scroll:
            self.chat_text.see(tk.END)
        elif preserve_scroll and saved_scroll:
            self.chat_text.yview_moveto(saved_scroll[0])
    
    def _toggle_wrap(self):
        self.wrapped = not self.wrapped
        if self.wrapped:
            self.h_scrollbar.grid_remove()
        else:
            self.h_scrollbar.grid()
        self._update_chat_display(preserve_scroll=True)
        self._update_status(f"Wrap: {'ON' if self.wrapped else 'OFF'}")
    
    def _toggle_markdown(self):
        self.markdown = not self.markdown
        self._update_chat_display(preserve_scroll=True)
        self._update_status(f"Mode: {'Markdown' if self.markdown else 'Raw Text'}")
    
    def _toggle_autoscroll(self):
        self.auto_scroll = not self.auto_scroll
        if HAVE_CTK:
            self.scroll_btn.configure(text=f"Autoscroll: {'ON' if self.auto_scroll else 'OFF'}")
        self._update_status(f"Autoscroll: {'ON' if self.auto_scroll else 'OFF'}")
    
    def _on_thinking_click(self, event):
        self.thinking_collapsed = not self.thinking_collapsed
        self._update_chat_display(preserve_scroll=True)
        self._update_status(f"Thinking: {'collapsed' if self.thinking_collapsed else 'expanded'}")
    
    def _update_status(self, text: str, color: str = None):
        """Update status label."""
        if HAVE_CTK:
            self.status_label.configure(text=text)
            if color:
                self.status_label.configure(text_color=color)
        else:
            self.status_label.configure(text=text)
    
    def _load_models(self):
        """Load available models in background."""
        if self._destroyed:
            return
        try:
            from ..api_client import fetch_models
            from .. import web_server
            
            models, error = fetch_models(web_server.CONFIG, web_server.KEY_MANAGERS)
            
            if models and not error and not self._destroyed:
                self.available_models = models
                model_ids = [m['id'] for m in models]
                
                def update_dropdown():
                    if self._destroyed:
                        return
                    try:
                        provider = web_server.CONFIG.get("default_provider", "google")
                        current = web_server.CONFIG.get(f"{provider}_model", "")
                        if HAVE_CTK:
                            self.model_dropdown.configure(values=model_ids)
                            if current and current in model_ids:
                                self.model_dropdown.set(current)
                            elif model_ids:
                                self.model_dropdown.set(current if current else model_ids[0])
                            else:
                                self.model_dropdown.set("(no models)")
                    except Exception:
                        pass
                
                self._safe_after(0, update_dropdown)
        except Exception as e:
            print(f"[StandaloneChatWindow] Error loading models: {e}")
    
    def _on_model_select(self, selected: str):
        """Handle model selection."""
        from ..config import save_config_value
        from .. import web_server
        
        if selected and selected not in ("(loading...)", "(no models)", "(default)"):
            self.selected_model = selected
            provider = web_server.CONFIG.get("default_provider", "google")
            config_key = f"{provider}_model"
            if save_config_value(config_key, selected):
                web_server.CONFIG[config_key] = selected
                self._update_status(f"✅ Model: {selected}", self.theme.accent_green)
            else:
                self._update_status(f"Model: {selected} (not saved)")
    
    def _send(self):
        """Send a message with streaming support."""
        if self.is_loading:
            return
        
        if HAVE_CTK:
            user_input = self.input_text.get("0.0", "end-1c").strip()
        else:
            user_input = self.input_text.get("1.0", tk.END).strip()
        
        placeholder = "Type your follow-up message here... (Ctrl+Enter to send)"
        
        if not user_input or user_input == placeholder:
            self._update_status("Please enter a message")
            return
        
        # Disable input
        self.is_loading = True
        if HAVE_CTK:
            self.send_btn.configure(state="disabled")
            self.input_text.configure(state="disabled")
        else:
            self.send_btn.configure(state=tk.DISABLED)
            self.input_text.configure(state=tk.DISABLED)
        self._update_status("Sending...")
        
        # Reset streaming state
        self.streaming_text = ""
        self.streaming_thinking = ""
        self.is_streaming = False
        self.last_usage = None
        
        def process_message():
            from .. import web_server
            from ..request_pipeline import RequestPipeline, RequestContext, RequestOrigin, StreamCallback
            
            self.session.add_message("user", user_input)
            
            # Update display and clear input
            def update_ui():
                self._update_chat_display(scroll_to_bottom=True)
                if HAVE_CTK:
                    self.input_text.configure(state="normal")
                    self.input_text.delete("0.0", "end")
                else:
                    self.input_text.configure(state=tk.NORMAL)
                    self.input_text.delete("1.0", tk.END)
            self._safe_after(0, update_ui)
            
            streaming_enabled = web_server.CONFIG.get("streaming_enabled", True)
            current_provider = web_server.CONFIG.get("default_provider", "google")
            current_model = self.selected_model or web_server.CONFIG.get(f"{current_provider}_model", "")
            
            ctx = RequestContext(
                origin=RequestOrigin.CHAT_WINDOW,
                provider=current_provider,
                model=current_model,
                streaming=streaming_enabled,
                thinking_enabled=web_server.CONFIG.get("thinking_enabled", False),
                session_id=str(self.session.session_id)
            )
            
            def on_text(content):
                if self._destroyed:
                    return
                self.streaming_text += content
                self._safe_after(0, self._update_streaming_display)
            
            def on_thinking(content):
                if self._destroyed:
                    return
                self.streaming_thinking += content
                self._safe_after(0, self._update_streaming_display)
            
            def on_usage(content):
                self.last_usage = content
            
            def on_error(content):
                if self._destroyed:
                    return
                self._safe_after(0, lambda: self._update_status(f"Error: {content}", self.theme.accent_red))
            
            callbacks = StreamCallback(
                on_text=on_text,
                on_thinking=on_thinking,
                on_usage=on_usage,
                on_error=on_error
            )
            
            self.is_streaming = True
            self._safe_after(0, lambda: self._update_status("Streaming..." if streaming_enabled else "Processing..."))
            
            if streaming_enabled and current_provider in ("custom", "google", "openrouter"):
                ctx = RequestPipeline.execute_streaming(
                    ctx, self.session, web_server.CONFIG, web_server.AI_PARAMS,
                    web_server.KEY_MANAGERS, callbacks
                )
            else:
                self.is_streaming = False
                messages = self.session.get_conversation_for_api(include_image=True)
                ctx = RequestPipeline.execute_simple(
                    ctx, messages, web_server.CONFIG, web_server.AI_PARAMS,
                    web_server.KEY_MANAGERS
                )
            
            self.is_streaming = False
            self.last_usage = {
                "prompt_tokens": ctx.input_tokens,
                "completion_tokens": ctx.output_tokens,
                "total_tokens": ctx.total_tokens,
                "estimated": ctx.estimated
            }
            
            if self._destroyed:
                return
            
            def handle_response():
                if self._destroyed:
                    return
                
                if ctx.error:
                    self._update_status(f"Error: {ctx.error}", self.theme.accent_red)
                    self.session.messages.pop()
                else:
                    self.session.add_message("assistant", ctx.response_text)
                    thinking_content = self.streaming_thinking or ctx.reasoning_text
                    if thinking_content and len(self.session.messages) > 0:
                        self.session.messages[-1]["thinking"] = thinking_content
                    
                    self.last_response = ctx.response_text
                    self._update_chat_display(scroll_to_bottom=True)
                    
                    usage_str = ""
                    if self.last_usage:
                        usage_str = f" | {self.last_usage.get('total_tokens', 0)} tokens"
                    
                    self._update_status(f"✅ Response received{usage_str}", self.theme.accent_green)
                    add_session(self.session, web_server.CONFIG.get("max_sessions", 50))
                
                self.is_loading = False
                if HAVE_CTK:
                    self.send_btn.configure(state="normal")
                    self.input_text.configure(state="normal")
                else:
                    self.send_btn.configure(state=tk.NORMAL)
                    self.input_text.configure(state=tk.NORMAL)
                
                self.streaming_text = ""
                self.streaming_thinking = ""
            
            self._safe_after(0, handle_response)
        
        threading.Thread(target=process_message, daemon=True).start()
    
    def _update_streaming_display(self):
        """Update display during streaming."""
        if not self.is_streaming or self._destroyed:
            return
        
        self.chat_text.configure(state=tk.NORMAL)
        
        try:
            last_sep_pos = self.chat_text.search("─" * 50, "end", backwards=True)
            if last_sep_pos:
                self.chat_text.delete(last_sep_pos, tk.END)
        except:
            pass
        
        self.chat_text.insert(tk.END, "─" * 50 + "\n", "separator")
        self.chat_text.insert(tk.END, "\nAssistant:\n", "assistant_label")
        
        if self.streaming_thinking:
            thinking_header = "▶ Thinking..." if self.thinking_collapsed else "▼ Thinking:"
            self.chat_text.insert(tk.END, f"{thinking_header}\n", "thinking_header")
            if not self.thinking_collapsed:
                self.chat_text.insert(tk.END, self.streaming_thinking + "\n", "thinking_content")
        
        if self.streaming_text:
            self.chat_text.insert(tk.END, self.streaming_text, "normal")
        else:
            self.chat_text.insert(tk.END, "...", "normal")
        
        self.chat_text.configure(state=tk.DISABLED)
        
        if self.auto_scroll:
            self.chat_text.see(tk.END)
    
    def _get_conversation_text(self) -> str:
        """Build conversation text for clipboard."""
        parts = []
        for msg in self.session.messages:
            role = "You" if msg["role"] == "user" else "Assistant"
            parts.append(f"[{role}]\n{msg['content']}\n")
        return "\n".join(parts)
    
    def _copy_all(self):
        text = self._get_conversation_text()
        if copy_to_clipboard(text, self.root):
            self._update_status("✅ Copied all!", self.theme.accent_green)
        else:
            self._update_status("✗ Failed to copy", self.theme.accent_red)
    
    def _copy_last(self):
        text = self.last_response
        if copy_to_clipboard(text, self.root):
            self._update_status("✅ Copied last response!", self.theme.accent_green)
        else:
            self._update_status("✗ Failed to copy", self.theme.accent_red)
    
    def _close(self):
        """Close window and cleanup."""
        self._destroyed = True
        self.is_streaming = False
        unregister_window(self.window_tag)
        
        try:
            if self.root:
                self.root.destroy()
        except tk.TclError:
            pass
        self.root = None


# =============================================================================
# Standalone Session Browser Window
# =============================================================================

class StandaloneSessionBrowserWindow:
    """
    Standalone session browser window that creates its own CTk root.
    Uses CTkScrollableFrame with custom SessionListItem widgets.
    """
    
    def __init__(self):
        self.window_id = get_next_window_id()
        self.window_tag = f"standalone_browser_{self.window_id}"
        
        self.selected_session_id = None
        self.selected_item: Optional[SessionListItem] = None
        
        # Theme
        self.theme = get_colors()
        self.colors = get_color_scheme()
        
        # Sorting state
        self.sort_column = "Updated"
        self.sort_descending = True
        
        self.root = None
        self._destroyed = False
        self.session_items: List[SessionListItem] = []
    
    def _safe_after(self, delay: int, func):
        """Schedule a callback only if window still exists."""
        if self._destroyed:
            return
        try:
            if self.root and self.root.winfo_exists():
                self.root.after(delay, func)
        except Exception:
            pass
    
    def show(self):
        """Create and show the window."""
        if HAVE_CTK:
            sync_ctk_appearance()
            self.root = ctk.CTk()
        else:
            self.root = tk.Tk()
        
        # Hide window while building UI (prevents elements appearing one by one)
        self.root.withdraw()
        
        self.root.title("Session Browser")
        self.root.geometry("880x520")
        self.root.minsize(600, 350)
        
        offset = (self.window_id % 3) * 30
        self.root.geometry(f"+{50 + offset}+{50 + offset}")
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        
        # Title with emoji image support
        if HAVE_CTK:
            title_emoji_img = None
            title_text = "📋 Saved Chat Sessions"
            if HAVE_EMOJI:
                renderer = get_emoji_renderer()
                title_emoji_img = renderer.get_ctk_image("📋", size=22)
                if title_emoji_img:
                    title_text = " Saved Chat Sessions"
            
            # Build title label kwargs - only include image/compound if we have an image
            title_label_kwargs = {
                "text": title_text,
                "font": get_ctk_font(size=16, weight="bold"),
                "text_color": self.theme.accent
            }
            if title_emoji_img:
                title_label_kwargs["image"] = title_emoji_img
                title_label_kwargs["compound"] = "left"
            
            ctk.CTkLabel(self.root, **title_label_kwargs).grid(row=0, column=0, sticky="w", padx=15, pady=(15, 10))
        
        # Session list container
        self._create_session_list()
        
        # Action buttons
        self._create_action_buttons()
        
        # Register and bind
        register_window(self.window_tag)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        
        # Load sessions
        self._refresh()
        
        # Force Tk to process all pending drawing commands before showing
        self.root.update_idletasks()
        
        # Show window after UI is fully rendered
        self.root.deiconify()
        
        # Set window icon AFTER deiconify (CTk overrides icon during setup)
        set_window_icon(self.root)
        
        # Focus
        self.root.lift()
        self.root.focus_force()
        
        # Run event loop
        self._run_event_loop()
    
    def _create_session_list(self):
        """Create the scrollable session list."""
        if HAVE_CTK:
            # Container frame
            list_container = ctk.CTkFrame(
                self.root,
                corner_radius=10,
                fg_color=self.theme.text_bg,
                border_color=self.theme.border,
                border_width=1
            )
            list_container.grid(row=1, column=0, sticky="nsew", padx=15, pady=5)
            list_container.columnconfigure(0, weight=1)
            list_container.rowconfigure(1, weight=1)
            
            # Header
            self.list_header = SessionListHeader(
                list_container,
                self.theme,
                on_sort=self._sort_by_column,
                current_sort=self.sort_column,
                descending=self.sort_descending
            )
            self.list_header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
            
            # Scrollable list
            self.session_list = ctk.CTkScrollableFrame(
                list_container,
                corner_radius=0,
                fg_color="transparent"
            )
            self.session_list.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
            self.session_list.columnconfigure(0, weight=1)
    
    def _create_action_buttons(self):
        """Create the action button row."""
        if HAVE_CTK:
            btn_frame = ctk.CTkFrame(self.root, fg_color="transparent")
            btn_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(10, 15))
            
            # Success button
            create_emoji_button(
                btn_frame, "New Session", "➕", self.theme, "success", 120, 32, self._new_session
            ).pack(side="left", padx=2)
            
            # Primary button
            create_emoji_button(
                btn_frame, "Open Chat", "💬", self.theme, "primary", 110, 32, self._open_session
            ).pack(side="left", padx=2)
            
            # Danger button
            create_emoji_button(
                btn_frame, "Delete", "🗑️", self.theme, "danger", 90, 32, self._delete_session
            ).pack(side="left", padx=2)
            
            # Secondary buttons
            create_emoji_button(
                btn_frame, "Refresh", "🔄", self.theme, "secondary", 90, 32, self._refresh
            ).pack(side="left", padx=2)
            
            create_emoji_button(
                btn_frame, "Close", "", self.theme, "secondary", 70, 32, self._close
            ).pack(side="left", padx=2)
            
            # Status label
            self.status_label = ctk.CTkLabel(
                btn_frame,
                text="Click on a session to select it",
                font=get_ctk_font(size=11),
                text_color=self.theme.overlay0
            )
            self.status_label.pack(side="left", padx=15)
    
    def _run_event_loop(self):
        """Run event loop."""
        try:
            while self.root is not None and not self._destroyed:
                try:
                    if not self.root.winfo_exists():
                        break
                    self.root.update()
                    time.sleep(0.01)
                except tk.TclError:
                    break
        except Exception:
            pass
    
    def _sort_by_column(self, column: str):
        """Sort by column."""
        if self.sort_column == column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column
            self.sort_descending = True
        
        # Update header indicators
        if HAVE_CTK:
            self.list_header.update_sort_indicators(self.sort_column, self.sort_descending)
        
        self._refresh()
    
    def _refresh(self):
        """Refresh the session list."""
        if self._destroyed:
            return
        
        # Clear existing items
        for item in self.session_items:
            item.destroy()
        self.session_items.clear()
        self.selected_item = None
        self.selected_session_id = None
        
        sessions = list_sessions()
        
        # Sort
        reverse = self.sort_descending
        if self.sort_column == "ID":
            sessions.sort(key=lambda s: s['id'] if isinstance(s['id'], int) else 0, reverse=reverse)
        elif self.sort_column == "Title":
            sessions.sort(key=lambda s: (s['title'] or '').lower(), reverse=reverse)
        elif self.sort_column == "Endpoint":
            sessions.sort(key=lambda s: s['endpoint'], reverse=reverse)
        elif self.sort_column == "Messages":
            sessions.sort(key=lambda s: s['messages'], reverse=reverse)
        elif self.sort_column == "Updated":
            sessions.sort(key=lambda s: s['updated'] or '', reverse=reverse)
        
        # Create items
        for session in sessions:
            if HAVE_CTK:
                item = SessionListItem(
                    self.session_list,
                    session,
                    self.theme,
                    on_click=self._on_select,
                    on_double_click=self._on_double_click
                )
                item.pack(fill="x", pady=1)
                self.session_items.append(item)
        
        self._update_status(f"{len(sessions)} session(s) found")
    
    def _on_select(self, session_data: Dict):
        """Handle session selection."""
        # Deselect previous
        if self.selected_item:
            self.selected_item.set_selected(False)
        
        # Find and select new
        self.selected_session_id = session_data.get('id')
        for item in self.session_items:
            if item.session_data.get('id') == self.selected_session_id:
                item.set_selected(True)
                self.selected_item = item
                break
        
        self._update_status(f"Selected: {self.selected_session_id}")
    
    def _on_double_click(self, session_data: Dict):
        """Handle double click to open session."""
        self._on_select(session_data)
        self._open_session()
    
    def _update_status(self, text: str):
        """Update status label."""
        if HAVE_CTK:
            self.status_label.configure(text=text)
    
    def _new_session(self):
        """Create a new session."""
        session = ChatSession(endpoint="chat")
        add_session(session)
        
        def open_chat():
            chat = StandaloneChatWindow(session)
            chat.show()
        threading.Thread(target=open_chat, daemon=True).start()
        
        self._refresh()
        self._update_status(f"Created new session {session.session_id}")
    
    def _open_session(self):
        """Open selected session."""
        if not self.selected_session_id:
            self._update_status("No session selected")
            return
        
        session = get_session(self.selected_session_id)
        if session:
            def open_chat():
                chat = StandaloneChatWindow(session)
                chat.show()
            threading.Thread(target=open_chat, daemon=True).start()
            self._update_status(f"Opened session {self.selected_session_id}")
        else:
            self._update_status("Session not found")
    
    def _delete_session(self):
        """Delete selected session."""
        if not self.selected_session_id:
            self._update_status("No session selected")
            return
        
        sid = self.selected_session_id
        if delete_session(sid):
            save_sessions()
            self.selected_session_id = None
            self.selected_item = None
            self._refresh()
            self._update_status(f"Deleted session {sid}")
        else:
            self._update_status("Failed to delete session")
    
    def _close(self):
        """Close window."""
        self._destroyed = True
        unregister_window(self.window_tag)
        try:
            if self.root:
                self.root.destroy()
        except tk.TclError:
            pass
        self.root = None


# =============================================================================
# Attached Windows (for GUICoordinator)
# =============================================================================

class AttachedChatWindow:
    """
    Chat window as CTkToplevel attached to coordinator's root.
    Used for centralized GUI threading.
    """
    
    def __init__(self, parent_root, session, initial_response: Optional[str] = None):
        self.session = session
        self.initial_response = initial_response
        self.parent_root = parent_root
        
        self.window_id = get_next_window_id()
        self.window_tag = f"attached_chat_{self.window_id}"
        
        # State
        self.wrapped = True
        self.markdown = True
        self.auto_scroll = True
        self.last_response = initial_response or ""
        self.is_loading = False
        self._destroyed = False
        
        # Initialize UI elements (to prevent AttributeError if creation fails)
        self.status_label = None
        self.wrap_btn = None
        self.md_btn = None
        self.scroll_btn = None
        self.send_btn = None
        self.input_text = None
        self.chat_text = None
        self.model_dropdown = None
        self.h_scrollbar = None
        self.v_scrollbar = None
        
        # Streaming state
        self.streaming_text = ""
        self.streaming_thinking = ""
        self.is_streaming = False
        self.thinking_collapsed = True
        self.last_usage = None
        
        # Models
        self.available_models = []
        from .. import web_server
        provider = web_server.CONFIG.get("default_provider", "google")
        self.selected_model = web_server.CONFIG.get(f"{provider}_model", "")
        
        # Theme
        self.theme = get_colors()
        self.colors = get_color_scheme()
        
        self._create_window()
    
    def _create_window(self):
        """Create the chat window as CTkToplevel."""
        if HAVE_CTK:
            self.root = ctk.CTkToplevel(self.parent_root)
        else:
            self.root = tk.Toplevel(self.parent_root)
        
        # Hide window while building UI
        self.root.withdraw()
        
        self.root.title(f"Chat - {self.session.title or self.session.session_id}")
        self.root.geometry("750x620")
        self.root.minsize(500, 400)
        
        offset = (self.window_id % 5) * 30
        self.root.geometry(f"+{80 + offset}+{80 + offset}")
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        
        # Build UI (same as standalone but using CTkToplevel)
        from .. import web_server
        current_provider = web_server.CONFIG.get("default_provider", "google")
        info_text = f"Session: {self.session.session_id} | Endpoint: /{self.session.endpoint} | Provider: {current_provider}"
        
        if HAVE_CTK:
            ctk.CTkLabel(
                self.root,
                text=info_text,
                font=get_ctk_font(size=11),
                text_color=self.theme.blockquote
            ).grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))
            
            # Toolbar
            self._create_toolbar()
            
            # Chat area
            self._create_chat_area()
            
            # Input area
            self._create_input_area()
            
            # Action buttons
            self._create_action_buttons()
        
        register_window(self.window_tag)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        
        self._update_chat_display(scroll_to_bottom=True)
        
        # Force Tk to process all pending drawing commands before showing
        self.root.update_idletasks()
        
        # Show window after UI is fully rendered
        self.root.deiconify()
        
        # Set window icon AFTER deiconify (CTk overrides icon during setup)
        set_window_icon(self.root)
        
        # Use after() for reliable focus on new window
        self.root.after(100, lambda: self._focus_window())
    
    def _focus_window(self):
        """Focus the window reliably."""
        if self._destroyed or not self.root:
            return
        try:
            self.root.lift()
            self.root.focus_force()
            # Temporarily set topmost to grab focus, then remove
            self.root.attributes('-topmost', True)
            self.root.after(150, lambda: self.root.attributes('-topmost', False) if self.root and not self._destroyed else None)
        except tk.TclError:
            pass
    
    def _create_toolbar(self):
        """Create toolbar."""
        btn_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=5)
        
        ctk.CTkLabel(
            btn_frame,
            text="Conversation:",
            font=get_ctk_font(size=12, weight="bold"),
            text_color=self.theme.accent
        ).pack(side="left", padx=(0, 10))
        
        btn_colors = get_ctk_button_colors(self.theme, "secondary")
        
        self.wrap_btn = ctk.CTkButton(
            btn_frame, text="Wrap: ON", font=get_ctk_font(size=11),
            width=85, height=28, corner_radius=6,
            command=self._toggle_wrap, **btn_colors
        )
        self.wrap_btn.pack(side="left", padx=2)
        
        self.md_btn = ctk.CTkButton(
            btn_frame, text="Markdown", font=get_ctk_font(size=11),
            width=85, height=28, corner_radius=6,
            command=self._toggle_markdown, **btn_colors
        )
        self.md_btn.pack(side="left", padx=2)
        
        self.scroll_btn = ctk.CTkButton(
            btn_frame, text="Autoscroll: ON", font=get_ctk_font(size=11),
            width=100, height=28, corner_radius=6,
            command=self._toggle_autoscroll, **btn_colors
        )
        self.scroll_btn.pack(side="left", padx=2)
        
        ctk.CTkLabel(
            btn_frame, text="Model:", font=get_ctk_font(size=11),
            text_color=self.theme.fg
        ).pack(side="left", padx=(15, 5))
        
        combo_colors = get_ctk_combobox_colors(self.theme)
        self.model_dropdown = ctk.CTkComboBox(
            btn_frame, values=["(loading...)"], width=220, height=28,
            corner_radius=6, command=self._on_model_select, **combo_colors
        )
        self.model_dropdown.pack(side="left", padx=5)
        self.model_dropdown.set(self.selected_model or "(default)")
        
        self.root.after(100, self._load_models)
    
    def _create_chat_area(self):
        """Create chat area."""
        chat_frame = ctk.CTkFrame(
            self.root, corner_radius=10, fg_color=self.theme.text_bg,
            border_color=self.theme.border, border_width=1
        )
        chat_frame.grid(row=2, column=0, sticky="nsew", padx=15, pady=5)
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)
        
        self.chat_text = tk.Text(
            chat_frame, wrap=tk.WORD, font=("Segoe UI", 11),
            bg=self.theme.text_bg, fg=self.theme.fg,
            insertbackground=self.theme.fg, relief=tk.FLAT,
            highlightthickness=0, padx=12, pady=12, borderwidth=0
        )
        self.chat_text.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        
        scrollbar_colors = get_ctk_scrollbar_colors(self.theme)
        self.v_scrollbar = ctk.CTkScrollbar(
            chat_frame, command=self.chat_text.yview,
            corner_radius=4, width=14, **scrollbar_colors
        )
        self.v_scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=8)
        self.chat_text.configure(yscrollcommand=self.v_scrollbar.set)
        
        self.h_scrollbar = ctk.CTkScrollbar(
            chat_frame, orientation="horizontal", command=self.chat_text.xview,
            corner_radius=4, height=14, **scrollbar_colors
        )
        self.h_scrollbar.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        self.h_scrollbar.grid_remove()
        self.chat_text.configure(xscrollcommand=self.h_scrollbar.set)
        
        setup_text_tags(self.chat_text, self.colors)
        self.chat_text.tag_bind("thinking_header", "<Button-1>", self._on_thinking_click)
    
    def _create_input_area(self):
        """Create input area."""
        ctk.CTkLabel(
            self.root, text="Your message:",
            font=get_ctk_font(size=12, weight="bold"),
            text_color=self.theme.accent
        ).grid(row=3, column=0, sticky="w", padx=15, pady=(10, 5))
        
        input_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        input_frame.grid(row=4, column=0, sticky="ew", padx=15, pady=5)
        input_frame.columnconfigure(0, weight=1)
        
        # Use textbox colors (no placeholder_text_color - not supported by CTkTextbox)
        textbox_colors = get_ctk_textbox_colors(self.theme)
        self.input_text = ctk.CTkTextbox(
            input_frame, height=75, font=get_ctk_font(size=12),
            corner_radius=8, border_width=1, wrap="word", **textbox_colors
        )
        self.input_text.grid(row=0, column=0, sticky="ew")
        
        placeholder = "Type your follow-up message here... (Ctrl+Enter to send)"
        self.input_text.insert("0.0", placeholder)
        self.input_text.configure(text_color=self.theme.overlay0)
        
        def on_focus_in(event):
            content = self.input_text.get("0.0", "end-1c")
            if content == placeholder:
                self.input_text.delete("0.0", "end")
                self.input_text.configure(text_color=self.theme.fg)
        
        def on_focus_out(event):
            content = self.input_text.get("0.0", "end-1c").strip()
            if not content:
                self.input_text.insert("0.0", placeholder)
                self.input_text.configure(text_color=self.theme.overlay0)
        
        self.input_text.bind('<FocusIn>', on_focus_in)
        self.input_text.bind('<FocusOut>', on_focus_out)
        self.input_text.bind('<Control-Return>', lambda e: self._send())
    
    def _create_action_buttons(self):
        """Create action buttons."""
        btn_row = ctk.CTkFrame(self.root, fg_color="transparent")
        btn_row.grid(row=5, column=0, sticky="ew", padx=15, pady=(5, 15))
        
        send_colors = get_ctk_button_colors(self.theme, "success")
        self.send_btn = ctk.CTkButton(
            btn_row, text="Send", font=get_ctk_font(size=12, weight="bold"),
            width=80, height=32, corner_radius=8,
            command=self._send, **send_colors
        )
        self.send_btn.pack(side="left", padx=2)
        
        sec_colors = get_ctk_button_colors(self.theme, "secondary")
        for text, cmd, width in [
            ("Copy All", self._copy_all, 85),
            ("Copy Last", self._copy_last, 85),
            ("Close", self._close, 70)
        ]:
            ctk.CTkButton(
                btn_row, text=text, font=get_ctk_font(size=12),
                width=width, height=32, corner_radius=8,
                command=cmd, **sec_colors
            ).pack(side="left", padx=2)
        
        self.status_label = ctk.CTkLabel(
            btn_row, text="", font=get_ctk_font(size=11),
            text_color=self.theme.accent_green
        )
        self.status_label.pack(side="left", padx=15)
    
    def _run_on_gui_thread(self, func):
        """Run callback on GUI thread."""
        if self._destroyed:
            return
        from .core import GUICoordinator
        
        def safe_wrapper():
            if not self._destroyed:
                try:
                    func()
                except tk.TclError:
                    pass
        
        GUICoordinator.get_instance().run_on_gui_thread(safe_wrapper)
    
    def _safe_after(self, delay: int, func):
        """Schedule callback safely."""
        if self._destroyed:
            return
        if delay == 0:
            self._run_on_gui_thread(func)
        else:
            try:
                if self.root and self.root.winfo_exists():
                    self.root.after(delay, func)
            except Exception:
                pass
    
    def _update_chat_display(self, scroll_to_bottom: bool = False, preserve_scroll: bool = False):
        """Update chat display."""
        if self._destroyed or not self.chat_text:
            return
        
        saved_scroll = None
        if preserve_scroll:
            saved_scroll = self.chat_text.yview()
        
        self.chat_text.configure(state=tk.NORMAL)
        self.chat_text.delete("1.0", tk.END)
        
        # Update button labels (with null checks)
        if self.wrap_btn:
            self.wrap_btn.configure(text=f"Wrap: {'ON' if self.wrapped else 'OFF'}")
        if self.md_btn:
            self.md_btn.configure(text="Markdown" if self.markdown else "Raw Text")
        if self.scroll_btn:
            self.scroll_btn.configure(text=f"Autoscroll: {'ON' if self.auto_scroll else 'OFF'}")
        
        for i, msg in enumerate(self.session.messages):
            role = msg["role"]
            content = msg["content"]
            thinking = msg.get("thinking", "")
            
            if i > 0:
                self.chat_text.insert(tk.END, "\n")
            
            if role == "user":
                self.chat_text.insert(tk.END, "You:\n", "user_label")
            else:
                self.chat_text.insert(tk.END, "Assistant:\n", "assistant_label")
            
            if role == "assistant" and thinking:
                thinking_header = "▶ Thinking (click to expand)..." if self.thinking_collapsed else "▼ Thinking:"
                self.chat_text.insert(tk.END, f"{thinking_header}\n", "thinking_header")
                if not self.thinking_collapsed:
                    self.chat_text.insert(tk.END, thinking + "\n\n", "thinking_content")
            
            if self.markdown:
                role_for_bg = "user" if role == "user" else "assistant"
                render_markdown(content, self.chat_text, self.colors,
                              wrap=self.wrapped, as_role=role_for_bg)
            else:
                self.chat_text.configure(wrap=tk.WORD if self.wrapped else tk.NONE)
                self.chat_text.insert(tk.END, content, "normal")
            
            self.chat_text.insert(tk.END, "\n" + "─" * 50 + "\n", "separator")
        
        self.chat_text.configure(state=tk.DISABLED)
        
        if scroll_to_bottom and self.auto_scroll:
            self.chat_text.see(tk.END)
        elif preserve_scroll and saved_scroll:
            self.chat_text.yview_moveto(saved_scroll[0])
    
    def _toggle_wrap(self):
        self.wrapped = not self.wrapped
        if self.h_scrollbar:
            if self.wrapped:
                self.h_scrollbar.grid_remove()
            else:
                self.h_scrollbar.grid()
        self._update_chat_display(preserve_scroll=True)
        self._update_status(f"Wrap: {'ON' if self.wrapped else 'OFF'}")
    
    def _toggle_markdown(self):
        self.markdown = not self.markdown
        self._update_chat_display(preserve_scroll=True)
        self._update_status(f"Mode: {'Markdown' if self.markdown else 'Raw Text'}")
    
    def _toggle_autoscroll(self):
        self.auto_scroll = not self.auto_scroll
        if self.scroll_btn:
            self.scroll_btn.configure(text=f"Autoscroll: {'ON' if self.auto_scroll else 'OFF'}")
        self._update_status(f"Autoscroll: {'ON' if self.auto_scroll else 'OFF'}")
    
    def _on_thinking_click(self, event):
        self.thinking_collapsed = not self.thinking_collapsed
        self._update_chat_display(preserve_scroll=True)
        self._update_status(f"Thinking: {'collapsed' if self.thinking_collapsed else 'expanded'}")
    
    def _update_status(self, text: str, color: str = None):
        """Update status label (with null check)."""
        if not self.status_label:
            return
        self.status_label.configure(text=text)
        if color:
            self.status_label.configure(text_color=color)
    
    def _load_models(self):
        """Load models."""
        if self._destroyed:
            return
        try:
            from ..api_client import fetch_models
            from .. import web_server
            
            def do_load():
                models, error = fetch_models(web_server.CONFIG, web_server.KEY_MANAGERS)
                if models and not error and not self._destroyed:
                    self.available_models = models
                    model_ids = [m['id'] for m in models]
                    
                    def update_ui():
                        if self._destroyed:
                            return
                        try:
                            provider = web_server.CONFIG.get("default_provider", "google")
                            current = web_server.CONFIG.get(f"{provider}_model", "")
                            self.model_dropdown.configure(values=model_ids)
                            if current and current in model_ids:
                                self.model_dropdown.set(current)
                            elif model_ids:
                                self.model_dropdown.set(current if current else model_ids[0])
                        except Exception:
                            pass
                    
                    self._safe_after(0, update_ui)
            
            threading.Thread(target=do_load, daemon=True).start()
        except Exception as e:
            print(f"[AttachedChatWindow] Error loading models: {e}")
    
    def _on_model_select(self, selected: str):
        from ..config import save_config_value
        from .. import web_server
        
        if selected and selected not in ("(loading...)", "(no models)", "(default)"):
            self.selected_model = selected
            provider = web_server.CONFIG.get("default_provider", "google")
            config_key = f"{provider}_model"
            if save_config_value(config_key, selected):
                web_server.CONFIG[config_key] = selected
                self._update_status(f"✅ Model: {selected}", self.theme.accent_green)
    
    def _send(self):
        """Send message."""
        if self.is_loading or self._destroyed:
            return
        
        user_input = self.input_text.get("0.0", "end-1c").strip()
        placeholder = "Type your follow-up message here... (Ctrl+Enter to send)"
        
        if not user_input or user_input == placeholder:
            self._update_status("Please enter a message")
            return
        
        self.is_loading = True
        self.send_btn.configure(state="disabled")
        self.input_text.configure(state="disabled")
        self._update_status("Sending...")
        
        self.streaming_text = ""
        self.streaming_thinking = ""
        self.is_streaming = False
        self.last_usage = None
        
        def process_message():
            from .. import web_server
            from ..request_pipeline import RequestPipeline, RequestContext, RequestOrigin, StreamCallback
            
            self.session.add_message("user", user_input)
            
            def update_ui():
                self._update_chat_display(scroll_to_bottom=True)
                self.input_text.configure(state="normal")
                self.input_text.delete("0.0", "end")
            self._safe_after(0, update_ui)
            
            streaming_enabled = web_server.CONFIG.get("streaming_enabled", True)
            current_provider = web_server.CONFIG.get("default_provider", "google")
            current_model = self.selected_model or web_server.CONFIG.get(f"{current_provider}_model", "")
            
            ctx = RequestContext(
                origin=RequestOrigin.CHAT_WINDOW,
                provider=current_provider,
                model=current_model,
                streaming=streaming_enabled,
                thinking_enabled=web_server.CONFIG.get("thinking_enabled", False),
                session_id=str(self.session.session_id)
            )
            
            def on_text(content):
                if self._destroyed:
                    return
                self.streaming_text += content
                self._safe_after(0, self._update_streaming_display)
            
            def on_thinking(content):
                if self._destroyed:
                    return
                self.streaming_thinking += content
                self._safe_after(0, self._update_streaming_display)
            
            def on_usage(content):
                self.last_usage = content
            
            def on_error(content):
                if self._destroyed:
                    return
                self._safe_after(0, lambda: self._update_status(f"Error: {content}", self.theme.accent_red))
            
            callbacks = StreamCallback(
                on_text=on_text,
                on_thinking=on_thinking,
                on_usage=on_usage,
                on_error=on_error
            )
            
            self.is_streaming = True
            self._safe_after(0, lambda: self._update_status("Streaming..." if streaming_enabled else "Processing..."))
            
            if streaming_enabled and current_provider in ("custom", "google", "openrouter"):
                ctx = RequestPipeline.execute_streaming(
                    ctx, self.session, web_server.CONFIG, web_server.AI_PARAMS,
                    web_server.KEY_MANAGERS, callbacks
                )
            else:
                self.is_streaming = False
                messages = self.session.get_conversation_for_api(include_image=True)
                ctx = RequestPipeline.execute_simple(
                    ctx, messages, web_server.CONFIG, web_server.AI_PARAMS,
                    web_server.KEY_MANAGERS
                )
            
            self.is_streaming = False
            self.last_usage = {
                "prompt_tokens": ctx.input_tokens,
                "completion_tokens": ctx.output_tokens,
                "total_tokens": ctx.total_tokens,
                "estimated": ctx.estimated
            }
            
            if self._destroyed:
                return
            
            def handle_response():
                if self._destroyed:
                    return
                
                if ctx.error:
                    self._update_status(f"Error: {ctx.error}", self.theme.accent_red)
                    self.session.messages.pop()
                else:
                    self.session.add_message("assistant", ctx.response_text)
                    thinking_content = self.streaming_thinking or ctx.reasoning_text
                    if thinking_content and len(self.session.messages) > 0:
                        self.session.messages[-1]["thinking"] = thinking_content
                    
                    self.last_response = ctx.response_text
                    self._update_chat_display(scroll_to_bottom=True)
                    
                    usage_str = ""
                    if self.last_usage:
                        usage_str = f" | {self.last_usage.get('total_tokens', 0)} tokens"
                    
                    self._update_status(f"✅ Response received{usage_str}", self.theme.accent_green)
                    add_session(self.session, web_server.CONFIG.get("max_sessions", 50))
                
                self.is_loading = False
                self.send_btn.configure(state="normal")
                self.input_text.configure(state="normal")
                self.streaming_text = ""
                self.streaming_thinking = ""
            
            self._safe_after(0, handle_response)
        
        threading.Thread(target=process_message, daemon=True).start()
    
    def _update_streaming_display(self):
        """Update streaming display."""
        if not self.is_streaming or self._destroyed:
            return
        
        self.chat_text.configure(state=tk.NORMAL)
        
        try:
            last_sep_pos = self.chat_text.search("─" * 50, "end", backwards=True)
            if last_sep_pos:
                self.chat_text.delete(last_sep_pos, tk.END)
        except:
            pass
        
        self.chat_text.insert(tk.END, "─" * 50 + "\n", "separator")
        self.chat_text.insert(tk.END, "\nAssistant:\n", "assistant_label")
        
        if self.streaming_thinking:
            thinking_header = "▶ Thinking..." if self.thinking_collapsed else "▼ Thinking:"
            self.chat_text.insert(tk.END, f"{thinking_header}\n", "thinking_header")
            if not self.thinking_collapsed:
                self.chat_text.insert(tk.END, self.streaming_thinking + "\n", "thinking_content")
        
        if self.streaming_text:
            self.chat_text.insert(tk.END, self.streaming_text, "normal")
        else:
            self.chat_text.insert(tk.END, "...", "normal")
        
        self.chat_text.configure(state=tk.DISABLED)
        
        if self.auto_scroll:
            self.chat_text.see(tk.END)
    
    def _get_conversation_text(self) -> str:
        parts = []
        for msg in self.session.messages:
            role = "You" if msg["role"] == "user" else "Assistant"
            parts.append(f"[{role}]\n{msg['content']}\n")
        return "\n".join(parts)
    
    def _copy_all(self):
        text = self._get_conversation_text()
        if copy_to_clipboard(text, self.root):
            self._update_status("✅ Copied all!", self.theme.accent_green)
        else:
            self._update_status("✗ Failed to copy", self.theme.accent_red)
    
    def _copy_last(self):
        text = self.last_response
        if copy_to_clipboard(text, self.root):
            self._update_status("✅ Copied last response!", self.theme.accent_green)
        else:
            self._update_status("✗ Failed to copy", self.theme.accent_red)
    
    def _close(self):
        self._destroyed = True
        self.is_streaming = False
        unregister_window(self.window_tag)
        
        try:
            if self.root:
                self.root.destroy()
        except tk.TclError:
            pass
        self.root = None


class AttachedBrowserWindow:
    """
    Session browser as CTkToplevel attached to coordinator's root.
    """
    
    def __init__(self, parent_root):
        self.parent_root = parent_root
        self.window_id = get_next_window_id()
        self.window_tag = f"attached_browser_{self.window_id}"
        
        self.selected_session_id = None
        self.selected_item: Optional[SessionListItem] = None
        
        self.theme = get_colors()
        self.colors = get_color_scheme()
        
        self.sort_column = "Updated"
        self.sort_descending = True
        
        self._destroyed = False
        self.session_items: List[SessionListItem] = []
        
        self._create_window()
    
    def _create_window(self):
        """Create browser window."""
        if HAVE_CTK:
            self.root = ctk.CTkToplevel(self.parent_root)
        else:
            self.root = tk.Toplevel(self.parent_root)
        
        # Hide window while building UI
        self.root.withdraw()
        
        self.root.title("Session Browser")
        self.root.geometry("880x520")
        self.root.minsize(600, 350)
        
        offset = (self.window_id % 3) * 30
        self.root.geometry(f"+{50 + offset}+{50 + offset}")
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        
        if HAVE_CTK:
            # Title with emoji image support
            title_emoji_img = None
            title_text = "📋 Saved Chat Sessions"
            if HAVE_EMOJI:
                renderer = get_emoji_renderer()
                title_emoji_img = renderer.get_ctk_image("📋", size=22)
                if title_emoji_img:
                    title_text = " Saved Chat Sessions"
            
            # Build title label kwargs - only include image/compound if we have an image
            title_label_kwargs = {
                "text": title_text,
                "font": get_ctk_font(size=16, weight="bold"),
                "text_color": self.theme.accent
            }
            if title_emoji_img:
                title_label_kwargs["image"] = title_emoji_img
                title_label_kwargs["compound"] = "left"
            
            ctk.CTkLabel(self.root, **title_label_kwargs).grid(row=0, column=0, sticky="w", padx=15, pady=(15, 10))
            
            # List container
            list_container = ctk.CTkFrame(
                self.root, corner_radius=10, fg_color=self.theme.text_bg,
                border_color=self.theme.border, border_width=1
            )
            list_container.grid(row=1, column=0, sticky="nsew", padx=15, pady=5)
            list_container.columnconfigure(0, weight=1)
            list_container.rowconfigure(1, weight=1)
            
            self.list_header = SessionListHeader(
                list_container, self.theme,
                on_sort=self._sort_by_column,
                current_sort=self.sort_column,
                descending=self.sort_descending
            )
            self.list_header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
            
            self.session_list = ctk.CTkScrollableFrame(
                list_container, corner_radius=0, fg_color="transparent"
            )
            self.session_list.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
            self.session_list.columnconfigure(0, weight=1)
            
            # Action buttons
            self._create_action_buttons()
        
        register_window(self.window_tag)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        
        self._refresh()
        
        # Force Tk to process all pending drawing commands before showing
        self.root.update_idletasks()
        
        # Show window after UI is fully rendered
        self.root.deiconify()
        
        # Set window icon AFTER deiconify (CTk overrides icon during setup)
        set_window_icon(self.root)
        
        self.root.lift()
        self.root.focus_force()
    
    def _create_action_buttons(self):
        """Create action buttons."""
        btn_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        btn_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(10, 15))
        
        create_emoji_button(
            btn_frame, "New Session", "➕", self.theme, "success", 120, 32, self._new_session
        ).pack(side="left", padx=2)
        
        create_emoji_button(
            btn_frame, "Open Chat", "💬", self.theme, "primary", 110, 32, self._open_session
        ).pack(side="left", padx=2)
        
        create_emoji_button(
            btn_frame, "Delete", "🗑️", self.theme, "danger", 90, 32, self._delete_session
        ).pack(side="left", padx=2)
        
        create_emoji_button(
            btn_frame, "Refresh", "🔄", self.theme, "secondary", 90, 32, self._refresh
        ).pack(side="left", padx=2)
        
        create_emoji_button(
            btn_frame, "Close", "", self.theme, "secondary", 70, 32, self._close
        ).pack(side="left", padx=2)
        
        self.status_label = ctk.CTkLabel(
            btn_frame, text="Click on a session to select it",
            font=get_ctk_font(size=11), text_color=self.theme.overlay0
        )
        self.status_label.pack(side="left", padx=15)
    
    def _sort_by_column(self, column: str):
        if self.sort_column == column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column
            self.sort_descending = True
        
        if HAVE_CTK:
            self.list_header.update_sort_indicators(self.sort_column, self.sort_descending)
        self._refresh()
    
    def _refresh(self):
        if self._destroyed:
            return
        
        for item in self.session_items:
            item.destroy()
        self.session_items.clear()
        self.selected_item = None
        self.selected_session_id = None
        
        sessions = list_sessions()
        reverse = self.sort_descending
        
        if self.sort_column == "ID":
            sessions.sort(key=lambda s: s['id'] if isinstance(s['id'], int) else 0, reverse=reverse)
        elif self.sort_column == "Title":
            sessions.sort(key=lambda s: (s['title'] or '').lower(), reverse=reverse)
        elif self.sort_column == "Endpoint":
            sessions.sort(key=lambda s: s['endpoint'], reverse=reverse)
        elif self.sort_column == "Messages":
            sessions.sort(key=lambda s: s['messages'], reverse=reverse)
        elif self.sort_column == "Updated":
            sessions.sort(key=lambda s: s['updated'] or '', reverse=reverse)
        
        for session in sessions:
            if HAVE_CTK:
                item = SessionListItem(
                    self.session_list, session, self.theme,
                    on_click=self._on_select,
                    on_double_click=self._on_double_click
                )
                item.pack(fill="x", pady=1)
                self.session_items.append(item)
        
        self._update_status(f"{len(sessions)} session(s) found")
    
    def _on_select(self, session_data: Dict):
        if self.selected_item:
            self.selected_item.set_selected(False)
        
        self.selected_session_id = session_data.get('id')
        for item in self.session_items:
            if item.session_data.get('id') == self.selected_session_id:
                item.set_selected(True)
                self.selected_item = item
                break
        
        self._update_status(f"Selected: {self.selected_session_id}")
    
    def _on_double_click(self, session_data: Dict):
        self._on_select(session_data)
        self._open_session()
    
    def _update_status(self, text: str):
        if HAVE_CTK:
            self.status_label.configure(text=text)
    
    def _new_session(self):
        from .core import GUICoordinator
        session = ChatSession(endpoint="chat")
        add_session(session)
        GUICoordinator.get_instance().request_chat_window(session)
        self._refresh()
        self._update_status(f"Created new session {session.session_id}")
    
    def _open_session(self):
        if not self.selected_session_id:
            self._update_status("No session selected")
            return
        
        session = get_session(self.selected_session_id)
        if session:
            from .core import GUICoordinator
            GUICoordinator.get_instance().request_chat_window(session)
            self._update_status(f"Opened session {self.selected_session_id}")
        else:
            self._update_status("Session not found")
    
    def _delete_session(self):
        if not self.selected_session_id:
            self._update_status("No session selected")
            return
        
        sid = self.selected_session_id
        if delete_session(sid):
            save_sessions()
            self.selected_session_id = None
            self.selected_item = None
            self._refresh()
            self._update_status(f"Deleted session {sid}")
        else:
            self._update_status("Failed to delete session")
    
    def _close(self):
        self._destroyed = True
        unregister_window(self.window_tag)
        try:
            if self.root:
                self.root.destroy()
        except tk.TclError:
            pass
        self.root = None


# =============================================================================
# Factory Functions
# =============================================================================

def create_attached_chat_window(parent_root, session, initial_response: Optional[str] = None):
    """Create a chat window as Toplevel attached to parent root."""
    AttachedChatWindow(parent_root, session, initial_response)


def create_attached_browser_window(parent_root):
    """Create a session browser window as Toplevel attached to parent root."""
    AttachedBrowserWindow(parent_root)
