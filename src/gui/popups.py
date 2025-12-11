#!/usr/bin/env python3
"""
Popup windows for TextEditTool - input and prompt selection

Threading Note:
    Popups are shown from hotkey threads and create their own Tk roots.
    To avoid conflicts with other Tk instances (like session browser),
    we use a polling update loop instead of blocking mainloop().

Design:
    Modern Catppuccin-inspired color scheme with:
    - Segmented toggle for response mode selection
    - Carousel-based action buttons with pagination
    - Icon support for action buttons
"""

import logging
import math
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Dict, List, Tuple

try:
    import darkdetect
    HAVE_DARKDETECT = True
except ImportError:
    HAVE_DARKDETECT = False


# =============================================================================
# Color Palettes (Catppuccin-inspired)
# =============================================================================

class CatppuccinMocha:
    """Dark mode color palette (Catppuccin Mocha)"""
    base = "#1e1e2e"           # Primary background
    mantle = "#181825"         # Deeper background
    surface0 = "#313244"       # Elevated surfaces
    surface1 = "#45475a"       # Hover states
    surface2 = "#585b70"       # Borders
    overlay0 = "#6c7086"       # Muted text
    text = "#cdd6f4"           # Primary text
    subtext0 = "#a6adc8"       # Secondary text
    blue = "#89b4fa"           # Accent
    lavender = "#b4befe"       # Hover accent
    green = "#a6e3a1"          # Success
    peach = "#fab387"          # Warning
    red = "#f38ba8"            # Error


class CatppuccinLatte:
    """Light mode color palette (Catppuccin Latte)"""
    base = "#eff1f5"           # Primary background
    mantle = "#e6e9ef"         # Deeper background
    surface0 = "#ccd0da"       # Elevated surfaces
    surface1 = "#bcc0cc"       # Hover states
    surface2 = "#acb0be"       # Borders
    overlay0 = "#9ca0b0"       # Muted text
    text = "#4c4f69"           # Primary text
    subtext0 = "#6c6f85"       # Secondary text
    blue = "#1e66f5"           # Accent
    lavender = "#7287fd"       # Hover accent
    green = "#40a02b"          # Success
    peach = "#fe640b"          # Warning
    red = "#d20f39"            # Error


def is_dark_mode() -> bool:
    """Check if system is in dark mode."""
    if HAVE_DARKDETECT:
        try:
            return darkdetect.isDark()
        except Exception:
            pass
    return False


def get_colors():
    """Get the appropriate color palette based on system theme."""
    return CatppuccinMocha if is_dark_mode() else CatppuccinLatte


# =============================================================================
# Custom UI Components
# =============================================================================

class SegmentedToggle:
    """
    A segmented control for selecting between options.
    Similar to iOS/macOS segmented controls.
    """
    
    def __init__(
        self,
        parent: tk.Frame,
        options: List[Tuple[str, str]],  # [(display_text, value), ...]
        default_value: str = None,
        on_change: Optional[Callable[[str], None]] = None
    ):
        self.parent = parent
        self.options = options
        self.on_change = on_change
        self.current_value = default_value or options[0][1]
        
        self.colors = get_colors()
        self.segments: List[tk.Label] = []
        
        self._create_widget()
    
    def _create_widget(self):
        """Create the segmented toggle widget."""
        # Container frame with rounded appearance
        self.frame = tk.Frame(
            self.parent,
            bg=self.colors.surface0,
            highlightbackground=self.colors.surface2,
            highlightthickness=1
        )
        
        for i, (display_text, value) in enumerate(self.options):
            is_selected = value == self.current_value
            
            segment = tk.Label(
                self.frame,
                text=display_text,
                font=("Arial", 9),
                bg=self.colors.blue if is_selected else self.colors.surface0,
                fg="#ffffff" if is_selected else self.colors.text,
                padx=12,
                pady=4,
                cursor="hand2"
            )
            segment.pack(side=tk.LEFT)
            segment.bind('<Button-1>', lambda e, v=value: self._on_click(v))
            segment.bind('<Enter>', lambda e, seg=segment, v=value: self._on_hover(seg, v, True))
            segment.bind('<Leave>', lambda e, seg=segment, v=value: self._on_hover(seg, v, False))
            
            self.segments.append(segment)
    
    def _on_click(self, value: str):
        """Handle segment click."""
        if value != self.current_value:
            self.current_value = value
            self._update_segments()
            if self.on_change:
                self.on_change(value)
    
    def _on_hover(self, segment: tk.Label, value: str, entering: bool):
        """Handle hover effect."""
        if value == self.current_value:
            return  # Don't change selected segment
        
        if entering:
            segment.config(bg=self.colors.surface1)
        else:
            segment.config(bg=self.colors.surface0)
    
    def _update_segments(self):
        """Update segment appearance based on current value."""
        for segment, (_, value) in zip(self.segments, self.options):
            is_selected = value == self.current_value
            segment.config(
                bg=self.colors.blue if is_selected else self.colors.surface0,
                fg="#ffffff" if is_selected else self.colors.text
            )
    
    def get(self) -> str:
        """Get current value."""
        return self.current_value
    
    def pack(self, **kwargs):
        """Pack the widget."""
        self.frame.pack(**kwargs)


class Tooltip:
    """
    A tooltip that appears after hovering over a widget for a specified delay.
    """
    
    DELAY_MS = 500  # Default delay before showing tooltip
    
    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = None):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms or self.DELAY_MS
        self.tooltip_window: Optional[tk.Toplevel] = None
        self.after_id: Optional[str] = None
        self.colors = get_colors()
        
        self.widget.bind('<Enter>', self._on_enter)
        self.widget.bind('<Leave>', self._on_leave)
        self.widget.bind('<Button-1>', self._on_leave)  # Hide on click
    
    def _on_enter(self, event):
        """Schedule tooltip display."""
        self._cancel_scheduled()
        self.after_id = self.widget.after(self.delay_ms, self._show_tooltip)
    
    def _on_leave(self, event=None):
        """Cancel scheduled tooltip or hide if visible."""
        self._cancel_scheduled()
        self._hide_tooltip()
    
    def _cancel_scheduled(self):
        """Cancel any scheduled tooltip display."""
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
    
    def _show_tooltip(self):
        """Display the tooltip."""
        if not self.text:
            return
        
        self.after_id = None
        
        # Get widget position
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        
        # Create tooltip window
        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_attributes('-topmost', True)
        
        # Tooltip frame with border
        frame = tk.Frame(
            self.tooltip_window,
            bg=self.colors.surface0,
            highlightbackground=self.colors.surface2,
            highlightthickness=1
        )
        frame.pack()
        
        # Tooltip label
        label = tk.Label(
            frame,
            text=self.text,
            font=("Arial", 9),
            bg=self.colors.surface0,
            fg=self.colors.text,
            padx=8,
            pady=4,
            wraplength=300,
            justify=tk.LEFT
        )
        label.pack()
        
        # Position tooltip
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
    
    def _hide_tooltip(self):
        """Hide the tooltip."""
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


class CarouselButtonList:
    """
    A carousel-style list of buttons with pagination.
    Shows a configurable number of items per page with navigation arrows.
    Supports continuous scrolling (wraps around at ends).
    """
    
    DEFAULT_ITEMS_PER_PAGE = 4
    
    def __init__(
        self,
        parent: tk.Frame,
        items: List[Tuple[str, str, Optional[str], Optional[str]]],  # [(key, display_text, icon, tooltip), ...]
        on_click: Callable[[str], None],
        items_per_page: int = None
    ):
        self.parent = parent
        self.items = items
        self.on_click = on_click
        self.items_per_page = items_per_page or self.DEFAULT_ITEMS_PER_PAGE
        
        self.colors = get_colors()
        self.current_page = 0
        self.total_pages = max(1, math.ceil(len(items) / self.items_per_page))
        
        self.buttons_frame: Optional[tk.Frame] = None
        self.nav_frame: Optional[tk.Frame] = None
        self.dot_labels: List[tk.Label] = []
        self.tooltips: List[Tooltip] = []  # Keep references to prevent garbage collection
        
        self._create_widget()
    
    def _create_widget(self):
        """Create the carousel widget."""
        self.frame = tk.Frame(self.parent, bg=self.colors.base)
        
        # Main container with navigation arrows
        self.content_frame = tk.Frame(self.frame, bg=self.colors.base)
        self.content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left arrow (always show if multiple pages, for continuous navigation)
        if self.total_pages > 1:
            self.left_arrow = tk.Label(
                self.content_frame,
                text="◀",
                font=("Arial", 12),
                bg=self.colors.base,
                fg=self.colors.overlay0,
                padx=8,
                cursor="hand2"
            )
            self.left_arrow.pack(side=tk.LEFT, fill=tk.Y)
            self.left_arrow.bind('<Button-1>', lambda e: self._prev_page())
            self.left_arrow.bind('<Enter>', lambda e: self.left_arrow.config(fg=self.colors.text))
            self.left_arrow.bind('<Leave>', lambda e: self._update_arrow_colors())
        
        # Buttons container
        self.buttons_frame = tk.Frame(self.content_frame, bg=self.colors.base)
        self.buttons_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Right arrow
        if self.total_pages > 1:
            self.right_arrow = tk.Label(
                self.content_frame,
                text="▶",
                font=("Arial", 12),
                bg=self.colors.base,
                fg=self.colors.overlay0,
                padx=8,
                cursor="hand2"
            )
            self.right_arrow.pack(side=tk.RIGHT, fill=tk.Y)
            self.right_arrow.bind('<Button-1>', lambda e: self._next_page())
            self.right_arrow.bind('<Enter>', lambda e: self.right_arrow.config(fg=self.colors.text))
            self.right_arrow.bind('<Leave>', lambda e: self._update_arrow_colors())
        
        # Page dots (only if multiple pages)
        if self.total_pages > 1:
            self.nav_frame = tk.Frame(self.frame, bg=self.colors.base)
            self.nav_frame.pack(pady=(8, 0))
            
            for i in range(self.total_pages):
                dot = tk.Label(
                    self.nav_frame,
                    text="●" if i == 0 else "○",
                    font=("Arial", 8),
                    bg=self.colors.base,
                    fg=self.colors.blue if i == 0 else self.colors.overlay0,
                    padx=2,
                    cursor="hand2"
                )
                dot.pack(side=tk.LEFT)
                dot.bind('<Button-1>', lambda e, page=i: self._go_to_page(page))
                self.dot_labels.append(dot)
        
        # Render initial page
        self._render_page()
    
    def _render_page(self):
        """Render the current page of buttons."""
        # Clear existing buttons and tooltips
        for widget in self.buttons_frame.winfo_children():
            widget.destroy()
        self.tooltips.clear()
        
        # Get items for current page
        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_items = self.items[start_idx:end_idx]
        
        # Create buttons
        for i, item in enumerate(page_items):
            key = item[0]
            display_text = item[1]
            icon = item[2] if len(item) > 2 else None
            tooltip_text = item[3] if len(item) > 3 else None
            
            btn_frame = tk.Frame(self.buttons_frame, bg=self.colors.base)
            btn_frame.pack(fill=tk.X, pady=1)
            
            # Use a fixed-width format for icon to ensure alignment
            # All emojis take roughly 2 character widths, so we use consistent spacing
            if icon:
                text = f" {icon}   {display_text}"
            else:
                text = f"       {display_text}"  # 7 spaces to match icon width
            
            btn = tk.Label(
                btn_frame,
                text=text,
                font=("Arial", 10),
                bg=self.colors.surface0,
                fg=self.colors.text,
                anchor=tk.W,
                padx=8,
                pady=10,
                cursor="hand2"
            )
            btn.pack(fill=tk.X)
            
            # Hover effects
            btn.bind('<Enter>', lambda e, b=btn: b.config(bg=self.colors.surface1))
            btn.bind('<Leave>', lambda e, b=btn: b.config(bg=self.colors.surface0))
            btn.bind('<Button-1>', lambda e, k=key: self.on_click(k))
            
            # Add tooltip if provided
            if tooltip_text:
                tooltip = Tooltip(btn, tooltip_text)
                self.tooltips.append(tooltip)
        
        # Update arrow and dot states
        self._update_arrow_colors()
        self._update_dots()
    
    def _update_arrow_colors(self):
        """Update arrow colors (always active for continuous navigation)."""
        if self.total_pages <= 1:
            return
        
        # Arrows are always active in continuous mode
        self.left_arrow.config(fg=self.colors.overlay0)
        self.right_arrow.config(fg=self.colors.overlay0)
    
    def _update_dots(self):
        """Update dot indicators."""
        for i, dot in enumerate(self.dot_labels):
            if i == self.current_page:
                dot.config(text="●", fg=self.colors.blue)
            else:
                dot.config(text="○", fg=self.colors.overlay0)
    
    def _next_page(self):
        """Go to next page (wraps around to first page)."""
        self.current_page = (self.current_page + 1) % self.total_pages
        self._render_page()
    
    def _prev_page(self):
        """Go to previous page (wraps around to last page)."""
        self.current_page = (self.current_page - 1) % self.total_pages
        self._render_page()
    
    def _go_to_page(self, page: int):
        """Go to specific page."""
        if 0 <= page < self.total_pages:
            self.current_page = page
            self._render_page()
    
    def pack(self, **kwargs):
        """Pack the widget."""
        self.frame.pack(**kwargs)


# =============================================================================
# Base Popup Class
# =============================================================================

class BasePopup:
    """Base class for popup windows"""
    
    def __init__(self):
        self.root: Optional[tk.Tk] = None
        self.dark_mode = is_dark_mode()
        self.colors = get_colors()
        self._setup_colors()
    
    def _setup_colors(self):
        """Setup color scheme based on dark/light mode (legacy compatibility)."""
        c = self.colors
        self.bg_color = c.base
        self.fg_color = c.text
        self.button_bg = c.surface0
        self.button_hover = c.surface1
        self.input_bg = c.surface0
        self.border_color = c.surface2
        self.accent_color = c.blue
    
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
    
    Display Mode Override Hierarchy:
        1. Radio button selection (if not "Default") - highest priority
        2. show_ai_response_in_chat_window config setting
        3. Falls back to replace mode (False)
    """
    
    def __init__(
        self,
        on_submit: Callable[[str, str], None],  # (text, response_mode)
        on_close: Optional[Callable[[], None]] = None
    ):
        super().__init__()
        self.on_submit = on_submit
        self.on_close_callback = on_close
        self.input_var: Optional[tk.StringVar] = None
        self.response_mode_var: Optional[tk.StringVar] = None  # "default", "replace", "show"
    
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
        
        # Bind StringVar to THIS popup's root
        self.response_mode_var = tk.StringVar(master=self.root, value="default")
        
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
                highlightthickness=0,
                indicatoron=True
            )
            rb.pack(side=tk.LEFT, padx=2)
        
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
            activebackground="#1976D2",  # Darker blue for active state
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
        
        # Use polling update loop instead of mainloop() to avoid conflicts
        # with other Tk instances in different threads
        self._run_event_loop()
    
    def _run_event_loop(self):
        """Run event loop without blocking other Tk instances."""
        try:
            while self.root is not None:
                try:
                    if not self.root.winfo_exists():
                        break
                    self.root.update()
                    time.sleep(0.01)  # Small delay to avoid busy-waiting
                except tk.TclError:
                    break  # Window was destroyed
        except Exception as e:
            logging.debug(f"Popup event loop ended: {e}")
    
    def _submit(self):
        """Handle submit."""
        text = self.input_var.get().strip()
        if text and text != "Ask your AI...":
            response_mode = self.response_mode_var.get() if self.response_mode_var else "default"
            self._close()
            self.on_submit(text, response_mode)
    
    def _close(self):
        super()._close()
        if self.on_close_callback:
            self.on_close_callback()


class PromptSelectionPopup(BasePopup):
    """
    Popup with prompt selection buttons for when text is selected.
    Shows input field plus predefined prompt options.
    
    Display Mode Override Hierarchy:
        1. Radio button selection (if not "Default") - highest priority
        2. show_chat_window_instead_of_replace per-action setting
        3. Falls back to replace mode (False)
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
        
        # Bind StringVar to THIS popup's root, not any existing Tk instance
        self.response_mode_var = tk.StringVar(master=self.root, value="default")
        
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
                highlightthickness=0,
                indicatoron=True
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
            activebackground="#1976D2",  # Darker blue for active state
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
        
        # Use polling update loop instead of mainloop() to avoid conflicts
        # with other Tk instances in different threads
        self._run_event_loop()
    
    def _run_event_loop(self):
        """Run event loop without blocking other Tk instances."""
        try:
            while self.root is not None:
                try:
                    if not self.root.winfo_exists():
                        break
                    self.root.update()
                    time.sleep(0.01)  # Small delay to avoid busy-waiting
                except tk.TclError:
                    break  # Window was destroyed
        except Exception as e:
            logging.debug(f"Popup event loop ended: {e}")
    
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


# =============================================================================
# Attached Popups for GUICoordinator
# =============================================================================
# These create Toplevel windows attached to the coordinator's hidden root

class AttachedInputPopup:
    """
    Input popup as Toplevel attached to coordinator's root.
    Modern Catppuccin-styled with segmented toggle for response mode.
    """
    
    PLACEHOLDER = "Ask AI anything..."
    
    def __init__(
        self,
        parent_root: tk.Tk,
        on_submit: Callable[[str, str], None],
        on_close: Optional[Callable[[], None]] = None,
        x: Optional[int] = None,
        y: Optional[int] = None
    ):
        self.parent_root = parent_root
        self.on_submit = on_submit
        self.on_close_callback = on_close
        self.x = x
        self.y = y
        
        self.colors = get_colors()
        self.root: Optional[tk.Toplevel] = None
        self.input_var: Optional[tk.StringVar] = None
        self.response_toggle: Optional[SegmentedToggle] = None
        
        self._create_window()
    
    def _create_window(self):
        """Create the styled input popup window."""
        self.root = tk.Toplevel(self.parent_root)
        self.root.title("AI Chat")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg=self.colors.base)
        
        # Main frame with subtle border
        main_frame = tk.Frame(
            self.root,
            bg=self.colors.base,
            highlightbackground=self.colors.surface2,
            highlightthickness=1
        )
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        content_frame = tk.Frame(main_frame, bg=self.colors.base)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        
        # Top bar with close button
        top_bar = tk.Frame(content_frame, bg=self.colors.base)
        top_bar.pack(fill=tk.X, pady=(0, 8))
        
        close_btn = tk.Label(
            top_bar,
            text="×",
            font=("Arial", 16, "bold"),
            bg=self.colors.base,
            fg=self.colors.overlay0,
            cursor="hand2"
        )
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind('<Button-1>', lambda e: self._close())
        close_btn.bind('<Enter>', lambda e: close_btn.config(fg=self.colors.red))
        close_btn.bind('<Leave>', lambda e: close_btn.config(fg=self.colors.overlay0))
        
        # Response mode toggle (segmented control)
        toggle_frame = tk.Frame(content_frame, bg=self.colors.base)
        toggle_frame.pack(fill=tk.X, pady=(0, 12))
        
        self.response_toggle = SegmentedToggle(
            toggle_frame,
            options=[("Default", "default"), ("Replace", "replace"), ("Show", "show")],
            default_value="default"
        )
        self.response_toggle.pack(anchor=tk.CENTER)
        
        # Input area with modern styling
        input_frame = tk.Frame(content_frame, bg=self.colors.base)
        input_frame.pack(fill=tk.X)
        
        # Input container with border
        input_container = tk.Frame(
            input_frame,
            bg=self.colors.surface0,
            highlightbackground=self.colors.surface2,
            highlightthickness=1
        )
        input_container.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        
        self.input_var = tk.StringVar(master=self.root)
        
        self.input_entry = tk.Entry(
            input_container,
            textvariable=self.input_var,
            font=("Arial", 11),
            bg=self.colors.surface0,
            fg=self.colors.text,
            insertbackground=self.colors.text,
            relief=tk.FLAT,
            bd=0,
            width=35
        )
        self.input_entry.pack(fill=tk.X, padx=10, pady=10)
        self.input_entry.insert(0, self.PLACEHOLDER)
        self.input_entry.config(fg=self.colors.overlay0)
        
        self.input_entry.bind('<FocusIn>', self._on_focus_in)
        self.input_entry.bind('<FocusOut>', self._on_focus_out)
        self.input_entry.bind('<Return>', lambda e: self._submit())
        
        # Send button
        send_btn = tk.Label(
            input_frame,
            text="➤",
            font=("Arial", 14),
            bg=self.colors.blue,
            fg="#ffffff",
            padx=14,
            pady=8,
            cursor="hand2"
        )
        send_btn.pack(side=tk.RIGHT)
        send_btn.bind('<Button-1>', lambda e: self._submit())
        send_btn.bind('<Enter>', lambda e: send_btn.config(bg=self.colors.lavender))
        send_btn.bind('<Leave>', lambda e: send_btn.config(bg=self.colors.blue))
        
        # Position window
        self._position_window()
        
        # Bindings
        self.root.bind('<Escape>', lambda e: self._close())
        
        # Focus
        self.root.lift()
        self.root.focus_force()
        self.input_entry.focus_set()
    
    def _position_window(self):
        """Position the window near the cursor."""
        self.root.update_idletasks()
        
        x = self.x
        y = self.y
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
    
    def _on_focus_in(self, event):
        """Handle input focus in."""
        if self.input_entry.get() == self.PLACEHOLDER:
            self.input_entry.delete(0, tk.END)
            self.input_entry.config(fg=self.colors.text)
    
    def _on_focus_out(self, event):
        """Handle input focus out."""
        if not self.input_entry.get():
            self.input_entry.insert(0, self.PLACEHOLDER)
            self.input_entry.config(fg=self.colors.overlay0)
    
    def _submit(self):
        """Handle form submission."""
        text = self.input_var.get().strip()
        if text and text != self.PLACEHOLDER:
            response_mode = self.response_toggle.get() if self.response_toggle else "default"
            self._close()
            self.on_submit(text, response_mode)
    
    def _close(self):
        """Close the popup."""
        if self.root:
            try:
                self.root.destroy()
            except tk.TclError:
                pass
            self.root = None
        if self.on_close_callback:
            self.on_close_callback()


class AttachedPromptPopup:
    """
    Prompt selection popup as Toplevel attached to coordinator's root.
    Modern Catppuccin-styled with segmented toggle and carousel buttons.
    """
    
    PLACEHOLDER = "Describe your change..."
    
    def __init__(
        self,
        parent_root: tk.Tk,
        options: Dict,
        on_option_selected: Callable[[str, str, Optional[str], str], None],
        on_close: Optional[Callable[[], None]],
        selected_text: str,
        x: Optional[int] = None,
        y: Optional[int] = None
    ):
        self.parent_root = parent_root
        self.options = options
        self.on_option_selected = on_option_selected
        self.on_close_callback = on_close
        self.selected_text = selected_text
        self.x = x
        self.y = y
        
        self.colors = get_colors()
        self.root: Optional[tk.Toplevel] = None
        self.input_var: Optional[tk.StringVar] = None
        self.response_toggle: Optional[SegmentedToggle] = None
        
        self._create_window()
    
    def _create_window(self):
        """Create the styled prompt popup window."""
        self.root = tk.Toplevel(self.parent_root)
        self.root.title("Text Edit Tool")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg=self.colors.base)
        
        # Main frame with subtle border
        main_frame = tk.Frame(
            self.root,
            bg=self.colors.base,
            highlightbackground=self.colors.surface2,
            highlightthickness=1
        )
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        content_frame = tk.Frame(main_frame, bg=self.colors.base)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        
        # Top bar with close button
        top_bar = tk.Frame(content_frame, bg=self.colors.base)
        top_bar.pack(fill=tk.X, pady=(0, 8))
        
        close_btn = tk.Label(
            top_bar,
            text="×",
            font=("Arial", 16, "bold"),
            bg=self.colors.base,
            fg=self.colors.overlay0,
            cursor="hand2"
        )
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind('<Button-1>', lambda e: self._close())
        close_btn.bind('<Enter>', lambda e: close_btn.config(fg=self.colors.red))
        close_btn.bind('<Leave>', lambda e: close_btn.config(fg=self.colors.overlay0))
        
        # Response mode toggle (segmented control)
        toggle_frame = tk.Frame(content_frame, bg=self.colors.base)
        toggle_frame.pack(fill=tk.X, pady=(0, 12))
        
        self.response_toggle = SegmentedToggle(
            toggle_frame,
            options=[("Default", "default"), ("Replace", "replace"), ("Show", "show")],
            default_value="default"
        )
        self.response_toggle.pack(anchor=tk.CENTER)
        
        # Input area with modern styling
        input_frame = tk.Frame(content_frame, bg=self.colors.base)
        input_frame.pack(fill=tk.X, pady=(0, 12))
        
        # Input container with border
        input_container = tk.Frame(
            input_frame,
            bg=self.colors.surface0,
            highlightbackground=self.colors.surface2,
            highlightthickness=1
        )
        input_container.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        
        self.input_var = tk.StringVar(master=self.root)
        
        self.input_entry = tk.Entry(
            input_container,
            textvariable=self.input_var,
            font=("Arial", 11),
            bg=self.colors.surface0,
            fg=self.colors.text,
            insertbackground=self.colors.text,
            relief=tk.FLAT,
            bd=0
        )
        self.input_entry.pack(fill=tk.X, padx=10, pady=10)
        self.input_entry.insert(0, self.PLACEHOLDER)
        self.input_entry.config(fg=self.colors.overlay0)
        
        self.input_entry.bind('<FocusIn>', self._on_focus_in)
        self.input_entry.bind('<FocusOut>', self._on_focus_out)
        self.input_entry.bind('<Return>', lambda e: self._on_custom_submit())
        
        # Send button
        send_btn = tk.Label(
            input_frame,
            text="➤",
            font=("Arial", 14),
            bg=self.colors.blue,
            fg="#ffffff",
            padx=14,
            pady=8,
            cursor="hand2"
        )
        send_btn.pack(side=tk.RIGHT)
        send_btn.bind('<Button-1>', lambda e: self._on_custom_submit())
        send_btn.bind('<Enter>', lambda e: send_btn.config(bg=self.colors.lavender))
        send_btn.bind('<Leave>', lambda e: send_btn.config(bg=self.colors.blue))
        
        # Action buttons carousel
        self._create_carousel(content_frame)
        
        # Position window
        self._position_window()
        
        # Bindings
        self.root.bind('<Escape>', lambda e: self._close())
        
        # Focus
        self.root.lift()
        self.root.focus_force()
        self.input_entry.focus_set()
    
    def _create_carousel(self, parent: tk.Frame):
        """Create the carousel with action buttons."""
        # Get items per page from settings
        settings = self.options.get("_settings", {})
        items_per_page = settings.get("popup_items_per_page", CarouselButtonList.DEFAULT_ITEMS_PER_PAGE)
        
        # Build items list: (key, display_text, icon, tooltip)
        items = []
        for key, option in self.options.items():
            if key == "Custom" or key.startswith("_"):
                continue
            icon = option.get("icon", None)
            # Use the task description as tooltip
            tooltip = option.get("task", None)
            items.append((key, key, icon, tooltip))
        
        if items:
            carousel = CarouselButtonList(
                parent,
                items=items,
                on_click=self._on_option_click,
                items_per_page=items_per_page
            )
            carousel.pack(fill=tk.X)
    
    def _position_window(self):
        """Position the window near the cursor."""
        self.root.update_idletasks()
        
        x = self.x
        y = self.y
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
    
    def _on_focus_in(self, event):
        """Handle input focus in."""
        if self.input_entry.get() == self.PLACEHOLDER:
            self.input_entry.delete(0, tk.END)
            self.input_entry.config(fg=self.colors.text)
    
    def _on_focus_out(self, event):
        """Handle input focus out."""
        if not self.input_entry.get():
            self.input_entry.insert(0, self.PLACEHOLDER)
            self.input_entry.config(fg=self.colors.overlay0)
    
    def _on_option_click(self, option_key: str):
        """Handle action button click."""
        logging.debug(f'Option selected: {option_key}')
        response_mode = self.response_toggle.get() if self.response_toggle else "default"
        self._close()
        self.on_option_selected(option_key, self.selected_text, None, response_mode)
    
    def _on_custom_submit(self):
        """Handle custom input submission."""
        custom_text = self.input_var.get().strip()
        if not custom_text or custom_text == self.PLACEHOLDER:
            return
        
        logging.debug(f'Custom input submitted: {custom_text[:50]}...')
        response_mode = self.response_toggle.get() if self.response_toggle else "default"
        self._close()
        self.on_option_selected("Custom", self.selected_text, custom_text, response_mode)
    
    def _close(self):
        """Close the popup."""
        if self.root:
            try:
                self.root.destroy()
            except tk.TclError:
                pass
            self.root = None
        if self.on_close_callback:
            self.on_close_callback()


def create_attached_input_popup(
    parent_root: tk.Tk,
    on_submit: Callable[[str, str], None],
    on_close: Optional[Callable[[], None]],
    x: Optional[int] = None,
    y: Optional[int] = None
):
    """Create an input popup as Toplevel attached to parent root (called on GUI thread)"""
    AttachedInputPopup(parent_root, on_submit, on_close, x, y)


def create_attached_prompt_popup(
    parent_root: tk.Tk,
    options: Dict,
    on_option_selected: Callable[[str, str, Optional[str], str], None],
    on_close: Optional[Callable[[], None]],
    selected_text: str,
    x: Optional[int] = None,
    y: Optional[int] = None
):
    """Create a prompt selection popup as Toplevel attached to parent root (called on GUI thread)"""
    AttachedPromptPopup(parent_root, options, on_option_selected, on_close, selected_text, x, y)
