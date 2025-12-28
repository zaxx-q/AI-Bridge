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
    Uses add='+' to not override existing event bindings (like hover effects).
    """
    
    DELAY_MS = 500  # Default delay before showing tooltip
    
    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = None):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms or self.DELAY_MS
        self.tooltip_window: Optional[tk.Toplevel] = None
        self.after_id: Optional[str] = None
        self.colors = get_colors()
        
        # Use add='+' to add handlers without replacing existing ones (like hover effects)
        self.widget.bind('<Enter>', self._on_enter, add='+')
        self.widget.bind('<Leave>', self._on_leave, add='+')
        self.widget.bind('<Button-1>', self._on_leave, add='+')  # Hide on click
    
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


class GroupedButtonList:
    """
    A list of buttons organized by groups with inline headers.
    Each group displays all its items together without pagination.
    Groups flow continuously with headers appearing inline.
    """
    
    def __init__(
        self,
        parent: tk.Frame,
        groups: List[Dict],  # [{"name": "Group Name", "items": [(key, display_text, icon, tooltip), ...]}, ...]
        on_click: Callable[[str], None]
    ):
        self.parent = parent
        self.groups = groups
        self.on_click = on_click
        
        self.colors = get_colors()
        self.current_group_idx = 0
        self.total_groups = len(groups)
        
        self.buttons_frame: Optional[tk.Frame] = None
        self.nav_frame: Optional[tk.Frame] = None
        self.dot_labels: List[tk.Label] = []
        self.tooltips: List[Tooltip] = []
        self.group_header_label: Optional[tk.Label] = None
        
        self._create_widget()
    
    def _create_widget(self):
        """Create the grouped button list widget."""
        self.frame = tk.Frame(self.parent, bg=self.colors.base)
        
        # Main container with navigation arrows
        self.content_frame = tk.Frame(self.frame, bg=self.colors.base)
        self.content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left arrow (for navigating between groups)
        if self.total_groups > 1:
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
            self.left_arrow.bind('<Button-1>', lambda e: self._prev_group())
            self.left_arrow.bind('<Enter>', lambda e: self.left_arrow.config(fg=self.colors.text))
            self.left_arrow.bind('<Leave>', lambda e: self.left_arrow.config(fg=self.colors.overlay0))
        
        # Buttons container (includes header + buttons)
        self.buttons_container = tk.Frame(self.content_frame, bg=self.colors.base)
        self.buttons_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Right arrow
        if self.total_groups > 1:
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
            self.right_arrow.bind('<Button-1>', lambda e: self._next_group())
            self.right_arrow.bind('<Enter>', lambda e: self.right_arrow.config(fg=self.colors.text))
            self.right_arrow.bind('<Leave>', lambda e: self.right_arrow.config(fg=self.colors.overlay0))
        
        # Group dots (only if multiple groups)
        if self.total_groups > 1:
            self.nav_frame = tk.Frame(self.frame, bg=self.colors.base)
            self.nav_frame.pack(pady=(8, 0))
            
            for i in range(self.total_groups):
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
                dot.bind('<Button-1>', lambda e, idx=i: self._go_to_group(idx))
                self.dot_labels.append(dot)
        
        # Render initial group
        self._render_group()
    
    def _render_group(self):
        """Render the current group with header and buttons."""
        # Clear existing content
        for widget in self.buttons_container.winfo_children():
            widget.destroy()
        self.tooltips.clear()
        
        if not self.groups:
            return
        
        current_group = self.groups[self.current_group_idx]
        group_name = current_group.get("name", "")
        items = current_group.get("items", [])
        
        # Group header
        if group_name:
            header_frame = tk.Frame(self.buttons_container, bg=self.colors.base)
            header_frame.pack(fill=tk.X, pady=(0, 4))
            
            self.group_header_label = tk.Label(
                header_frame,
                text=f"── {group_name} ──",
                font=("Arial", 9, "bold"),
                bg=self.colors.base,
                fg=self.colors.overlay0
            )
            self.group_header_label.pack(anchor=tk.CENTER)
        
        # Buttons frame
        self.buttons_frame = tk.Frame(self.buttons_container, bg=self.colors.base)
        self.buttons_frame.pack(fill=tk.BOTH, expand=True)
        
        # Configure columns
        self.buttons_frame.columnconfigure(0, weight=0, minsize=40)  # Icon column
        self.buttons_frame.columnconfigure(1, weight=1)  # Text column
        
        # Create buttons
        for i, item in enumerate(items):
            key = item[0]
            display_text = item[1]
            icon = item[2] if len(item) > 2 else None
            tooltip_text = item[3] if len(item) > 3 else None
            
            # Row frame
            row_frame = tk.Frame(self.buttons_frame, bg=self.colors.surface0, cursor="hand2")
            row_frame.grid(row=i, column=0, columnspan=2, sticky=tk.EW, pady=1)
            
            row_frame.columnconfigure(0, weight=0, minsize=40)
            row_frame.columnconfigure(1, weight=1)
            
            # Icon label
            icon_label = tk.Label(
                row_frame,
                text=icon if icon else "",
                font=("Arial", 10),
                bg=self.colors.surface0,
                fg=self.colors.text,
                width=3,
                anchor=tk.CENTER,
                pady=10,
                cursor="hand2"
            )
            icon_label.grid(row=0, column=0, sticky=tk.W, padx=(8, 0))
            
            # Text label
            text_label = tk.Label(
                row_frame,
                text=display_text,
                font=("Arial", 10),
                bg=self.colors.surface0,
                fg=self.colors.text,
                anchor=tk.W,
                pady=10,
                cursor="hand2"
            )
            text_label.grid(row=0, column=1, sticky=tk.W, padx=(4, 8))
            
            # Hover effects
            def make_enter_handler(frame, icon_lbl, text_lbl):
                def handler(e):
                    frame.config(bg=self.colors.surface1)
                    icon_lbl.config(bg=self.colors.surface1)
                    text_lbl.config(bg=self.colors.surface1)
                return handler
            
            def make_leave_handler(frame, icon_lbl, text_lbl):
                def handler(e):
                    frame.config(bg=self.colors.surface0)
                    icon_lbl.config(bg=self.colors.surface0)
                    text_lbl.config(bg=self.colors.surface0)
                return handler
            
            def make_click_handler(k):
                return lambda e: self.on_click(k)
            
            enter_handler = make_enter_handler(row_frame, icon_label, text_label)
            leave_handler = make_leave_handler(row_frame, icon_label, text_label)
            click_handler = make_click_handler(key)
            
            for widget in (row_frame, icon_label, text_label):
                widget.bind('<Enter>', enter_handler)
                widget.bind('<Leave>', leave_handler)
                widget.bind('<Button-1>', click_handler)
            
            # Tooltip
            if tooltip_text:
                tooltip = Tooltip(text_label, tooltip_text)
                self.tooltips.append(tooltip)
        
        # Update dots
        self._update_dots()
    
    def _update_dots(self):
        """Update dot indicators."""
        for i, dot in enumerate(self.dot_labels):
            if i == self.current_group_idx:
                dot.config(text="●", fg=self.colors.blue)
            else:
                dot.config(text="○", fg=self.colors.overlay0)
    
    def _next_group(self):
        """Go to next group (wraps around)."""
        self.current_group_idx = (self.current_group_idx + 1) % self.total_groups
        self._render_group()
    
    def _prev_group(self):
        """Go to previous group (wraps around)."""
        self.current_group_idx = (self.current_group_idx - 1) % self.total_groups
        self._render_group()
    
    def _go_to_group(self, idx: int):
        """Go to specific group."""
        if 0 <= idx < self.total_groups:
            self.current_group_idx = idx
            self._render_group()
    
    def pack(self, **kwargs):
        """Pack the widget."""
        self.frame.pack(**kwargs)


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
        """Render the current page of buttons using grid layout for consistent alignment."""
        # Clear existing buttons and tooltips
        for widget in self.buttons_frame.winfo_children():
            widget.destroy()
        self.tooltips.clear()
        
        # Configure buttons_frame columns - icon column fixed, text column expands
        self.buttons_frame.columnconfigure(0, weight=0, minsize=40)  # Icon column - fixed width
        self.buttons_frame.columnconfigure(1, weight=1)  # Text column - expands
        
        # Get items for current page
        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_items = self.items[start_idx:end_idx]
        
        # Create buttons using grid with separate icon and text columns
        for i, item in enumerate(page_items):
            key = item[0]
            display_text = item[1]
            icon = item[2] if len(item) > 2 else None
            tooltip_text = item[3] if len(item) > 3 else None
            
            # Create a container frame for the entire row (for hover and click)
            row_frame = tk.Frame(self.buttons_frame, bg=self.colors.surface0, cursor="hand2")
            row_frame.grid(row=i, column=0, columnspan=2, sticky=tk.EW, pady=1)
            
            # Configure row_frame columns
            row_frame.columnconfigure(0, weight=0, minsize=40)  # Icon
            row_frame.columnconfigure(1, weight=1)  # Text
            
            # Icon label (fixed width)
            icon_label = tk.Label(
                row_frame,
                text=icon if icon else "",
                font=("Arial", 10),
                bg=self.colors.surface0,
                fg=self.colors.text,
                width=3,  # Fixed character width for icons
                anchor=tk.CENTER,
                pady=10,
                cursor="hand2"
            )
            icon_label.grid(row=0, column=0, sticky=tk.W, padx=(8, 0))
            
            # Text label (expands)
            text_label = tk.Label(
                row_frame,
                text=display_text,
                font=("Arial", 10),
                bg=self.colors.surface0,
                fg=self.colors.text,
                anchor=tk.W,
                pady=10,
                cursor="hand2"
            )
            text_label.grid(row=0, column=1, sticky=tk.W, padx=(4, 8))
            
            # Hover effects for the entire row
            def make_enter_handler(frame, icon_lbl, text_lbl):
                def handler(e):
                    frame.config(bg=self.colors.surface1)
                    icon_lbl.config(bg=self.colors.surface1)
                    text_lbl.config(bg=self.colors.surface1)
                return handler
            
            def make_leave_handler(frame, icon_lbl, text_lbl):
                def handler(e):
                    frame.config(bg=self.colors.surface0)
                    icon_lbl.config(bg=self.colors.surface0)
                    text_lbl.config(bg=self.colors.surface0)
                return handler
            
            def make_click_handler(k):
                return lambda e: self.on_click(k)
            
            enter_handler = make_enter_handler(row_frame, icon_label, text_label)
            leave_handler = make_leave_handler(row_frame, icon_label, text_label)
            click_handler = make_click_handler(key)
            
            # Bind to all three widgets
            for widget in (row_frame, icon_label, text_label):
                widget.bind('<Enter>', enter_handler)
                widget.bind('<Leave>', leave_handler)
                widget.bind('<Button-1>', click_handler)
            
            # Add tooltip to the text label (most useful target)
            if tooltip_text:
                tooltip = Tooltip(text_label, tooltip_text)
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
        placeholder = "Explain your changes.."
        
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
        
        if not custom_text or custom_text == "Explain your changes..":
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
    
    Features two input boxes:
    1. "Explain your changes..." - For edit-type prompts (Custom action)
    2. "Ask about this text..." - For Q&A-type prompts (general output rules)
    """
    
    PLACEHOLDER_EDIT = "Explain your changes..."
    PLACEHOLDER_ASK = "Ask about this text..."
    
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
        self.edit_input_var: Optional[tk.StringVar] = None  # For "Explain your changes..."
        self.ask_input_var: Optional[tk.StringVar] = None   # For "Ask about this text..."
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
        
        # === Input area 1: Edit/Custom changes ===
        # Container holding both input and button
        edit_container = tk.Frame(
            content_frame,
            bg=self.colors.surface0,
            highlightbackground=self.colors.surface2,
            highlightthickness=1
        )
        edit_container.pack(fill=tk.X, pady=(0, 8))
        
        # Edit send button (Right aligned inside container)
        edit_send_btn = tk.Label(
            edit_container,
            text="      ✏️",
            font=("Arial", 12),
            bg=self.colors.blue,
            fg="#ffffff",
            width=4,  # Fixed width for consistency
            pady=8,
            cursor="hand2"
        )
        edit_send_btn.pack(side=tk.RIGHT, fill=tk.Y)
        edit_send_btn.bind('<Button-1>', lambda e: self._on_custom_submit())
        edit_send_btn.bind('<Enter>', lambda e: edit_send_btn.config(bg=self.colors.lavender))
        edit_send_btn.bind('<Leave>', lambda e: edit_send_btn.config(bg=self.colors.blue))
        Tooltip(edit_send_btn, "Edit text with custom instructions")
        
        self.edit_input_var = tk.StringVar(master=self.root)
        
        self.edit_input_entry = tk.Entry(
            edit_container,
            textvariable=self.edit_input_var,
            font=("Arial", 11),
            bg=self.colors.surface0,
            fg=self.colors.text,
            insertbackground=self.colors.text,
            relief=tk.FLAT,
            bd=0
        )
        self.edit_input_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.edit_input_entry.insert(0, self.PLACEHOLDER_EDIT)
        self.edit_input_entry.config(fg=self.colors.overlay0)
        
        self.edit_input_entry.bind('<FocusIn>', lambda e: self._on_edit_focus_in())
        self.edit_input_entry.bind('<FocusOut>', lambda e: self._on_edit_focus_out())
        self.edit_input_entry.bind('<Return>', lambda e: self._on_custom_submit())
        
        # === Input area 2: Ask/Q&A about text ===
        # Container holding both input and button
        ask_container = tk.Frame(
            content_frame,
            bg=self.colors.surface0,
            highlightbackground=self.colors.surface2,
            highlightthickness=1
        )
        ask_container.pack(fill=tk.X, pady=(0, 12))
        
        # Ask send button (Right aligned inside container)
        ask_send_btn = tk.Label(
            ask_container,
            text="❓",
            font=("Arial", 12),
            bg=self.colors.green,
            fg="#ffffff",
            width=4,  # Fixed width for consistency
            pady=8,
            cursor="hand2"
        )
        ask_send_btn.pack(side=tk.RIGHT, fill=tk.Y)
        ask_send_btn.bind('<Button-1>', lambda e: self._on_ask_submit())
        ask_send_btn.bind('<Enter>', lambda e: ask_send_btn.config(bg=self.colors.peach))
        ask_send_btn.bind('<Leave>', lambda e: ask_send_btn.config(bg=self.colors.green))
        Tooltip(ask_send_btn, "Ask a question about the text")
        
        self.ask_input_var = tk.StringVar(master=self.root)
        
        self.ask_input_entry = tk.Entry(
            ask_container,
            textvariable=self.ask_input_var,
            font=("Arial", 11),
            bg=self.colors.surface0,
            fg=self.colors.text,
            insertbackground=self.colors.text,
            relief=tk.FLAT,
            bd=0
        )
        self.ask_input_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.ask_input_entry.insert(0, self.PLACEHOLDER_ASK)
        self.ask_input_entry.config(fg=self.colors.overlay0)
        
        self.ask_input_entry.bind('<FocusIn>', lambda e: self._on_ask_focus_in())
        self.ask_input_entry.bind('<FocusOut>', lambda e: self._on_ask_focus_out())
        self.ask_input_entry.bind('<Return>', lambda e: self._on_ask_submit())
        
        # Action buttons carousel
        self._create_carousel(content_frame)
        
        # Position window
        self._position_window()
        
        # Bindings
        self.root.bind('<Escape>', lambda e: self._close())
        
        # Focus
        self.root.lift()
        self.root.focus_force()
        self.edit_input_entry.focus_set()
    
    def _create_carousel(self, parent: tk.Frame):
        """Create the carousel with action buttons (grouped or flat mode)."""
        settings = self.options.get("_settings", {})
        use_groups = settings.get("popup_use_groups", False)
        
        if use_groups:
            # Grouped mode: organize buttons by groups defined in settings
            self._create_grouped_buttons(parent, settings)
        else:
            # Flat mode: simple paginated carousel
            self._create_flat_carousel(parent, settings)
    
    def _create_grouped_buttons(self, parent: tk.Frame, settings: Dict):
        """Create grouped button list from settings."""
        popup_groups = settings.get("popup_groups", [])
        
        if not popup_groups:
            # Fallback to flat mode if no groups defined
            self._create_flat_carousel(parent, settings)
            return
        
        # Build groups with items: [{"name": "...", "items": [(key, display, icon, tooltip), ...]}, ...]
        groups = []
        for group_def in popup_groups:
            group_name = group_def.get("name", "")
            item_keys = group_def.get("items", [])
            
            items = []
            for key in item_keys:
                option = self.options.get(key)
                if option and key != "Custom" and not key.startswith("_"):
                    icon = option.get("icon", None)
                    tooltip = option.get("task", None)
                    items.append((key, key, icon, tooltip))
            
            if items:
                groups.append({"name": group_name, "items": items})
        
        if groups:
            grouped_list = GroupedButtonList(
                parent,
                groups=groups,
                on_click=self._on_option_click
            )
            grouped_list.pack(fill=tk.X)
        else:
            # Fallback if all groups are empty
            self._create_flat_carousel(parent, settings)
    
    def _create_flat_carousel(self, parent: tk.Frame, settings: Dict):
        """Create flat paginated carousel."""
        items_per_page = settings.get("popup_items_per_page", CarouselButtonList.DEFAULT_ITEMS_PER_PAGE)
        
        # Build items list: (key, display_text, icon, tooltip)
        items = []
        for key, option in self.options.items():
            if key == "Custom" or key.startswith("_"):
                continue
            icon = option.get("icon", None)
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
    
    def _on_edit_focus_in(self):
        """Handle edit input focus in."""
        if self.edit_input_entry.get() == self.PLACEHOLDER_EDIT:
            self.edit_input_entry.delete(0, tk.END)
            self.edit_input_entry.config(fg=self.colors.text)
    
    def _on_edit_focus_out(self):
        """Handle edit input focus out."""
        if not self.edit_input_entry.get():
            self.edit_input_entry.insert(0, self.PLACEHOLDER_EDIT)
            self.edit_input_entry.config(fg=self.colors.overlay0)
    
    def _on_ask_focus_in(self):
        """Handle ask input focus in."""
        if self.ask_input_entry.get() == self.PLACEHOLDER_ASK:
            self.ask_input_entry.delete(0, tk.END)
            self.ask_input_entry.config(fg=self.colors.text)
    
    def _on_ask_focus_out(self):
        """Handle ask input focus out."""
        if not self.ask_input_entry.get():
            self.ask_input_entry.insert(0, self.PLACEHOLDER_ASK)
            self.ask_input_entry.config(fg=self.colors.overlay0)
    
    def _on_option_click(self, option_key: str):
        """Handle action button click."""
        logging.debug(f'Option selected: {option_key}')
        response_mode = self.response_toggle.get() if self.response_toggle else "default"
        self._close()
        self.on_option_selected(option_key, self.selected_text, None, response_mode)
    
    def _on_custom_submit(self):
        """Handle custom edit input submission."""
        custom_text = self.edit_input_var.get().strip()
        if not custom_text or custom_text == self.PLACEHOLDER_EDIT:
            return
        
        logging.debug(f'Custom edit submitted: {custom_text[:50]}...')
        response_mode = self.response_toggle.get() if self.response_toggle else "default"
        self._close()
        self.on_option_selected("Custom", self.selected_text, custom_text, response_mode)
    
    def _on_ask_submit(self):
        """Handle ask/Q&A input submission."""
        ask_text = self.ask_input_var.get().strip()
        if not ask_text or ask_text == self.PLACEHOLDER_ASK:
            return
        
        logging.debug(f'Ask question submitted: {ask_text[:50]}...')
        response_mode = self.response_toggle.get() if self.response_toggle else "default"
        self._close()
        # Use "_Ask" as a special key to indicate Q&A mode
        self.on_option_selected("_Ask", self.selected_text, ask_text, response_mode)
    
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


# =============================================================================
# Typing Indicator - Small tooltip that follows cursor during streaming
# =============================================================================

class TypingIndicator:
    """
    A small floating indicator that shows during streaming typing.
    Displays near the mouse cursor and shows abort hotkey.
    
    Features:
    - Shows customizable abort hotkey hint
    - Auto-dismisses when closed
    """
    
    OFFSET_X = 20  # Pixels to the right of cursor
    OFFSET_Y = 20  # Pixels below cursor
    
    def __init__(
        self,
        parent_root: tk.Tk,
        abort_hotkey: str = "Escape",
        on_dismiss: Optional[Callable[[], None]] = None
    ):
        self.parent_root = parent_root
        self.abort_hotkey = abort_hotkey
        self.on_dismiss = on_dismiss
        
        self.colors = get_colors()
        self.root: Optional[tk.Toplevel] = None
        self.is_visible = False
        
        self._create_window()
    
    def _create_window(self):
        """Create the indicator window."""
        self.root = tk.Toplevel(self.parent_root)
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg=self.colors.surface0)
        
        # Make it slightly transparent on Windows
        try:
            self.root.attributes('-alpha', 0.95)
        except tk.TclError:
            pass  # Transparency not supported
        
        # Main frame with border
        main_frame = tk.Frame(
            self.root,
            bg=self.colors.surface0,
            highlightbackground=self.colors.blue,
            highlightthickness=2
        )
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Content frame
        content_frame = tk.Frame(main_frame, bg=self.colors.surface0)
        content_frame.pack(padx=8, pady=6)
        
        # Typing indicator with animation emoji
        typing_label = tk.Label(
            content_frame,
            text="✍️ Typing...",
            font=("Arial", 10, "bold"),
            bg=self.colors.surface0,
            fg=self.colors.text
        )
        typing_label.pack(side=tk.LEFT)
        
        # Abort hint
        hotkey_display = self.abort_hotkey.title() if self.abort_hotkey else "Escape"
        abort_label = tk.Label(
            content_frame,
            text=f" [{hotkey_display} to abort]",
            font=("Arial", 9),
            bg=self.colors.surface0,
            fg=self.colors.overlay0
        )
        abort_label.pack(side=tk.LEFT)
        
        self.is_visible = True
        
        # Position initially
        self._update_position()
    
    def _update_position(self):
        """Set window position near cursor."""
        if not self.root or not self.is_visible:
            return
        
        try:
            # Get cursor position
            x = self.root.winfo_pointerx() + self.OFFSET_X
            y = self.root.winfo_pointery() + self.OFFSET_Y
            
            # Get screen dimensions
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            
            # Get window dimensions
            self.root.update_idletasks()
            window_width = self.root.winfo_width()
            window_height = self.root.winfo_height()
            
            # Adjust if would go off screen
            if x + window_width > screen_width:
                x = self.root.winfo_pointerx() - window_width - 10
            if y + window_height > screen_height:
                y = self.root.winfo_pointery() - window_height - 10
            
            self.root.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass  # Window was destroyed
    
    def dismiss(self):
        """Dismiss the indicator."""
        self.is_visible = False
        
        # Destroy window
        if self.root:
            try:
                self.root.destroy()
            except tk.TclError:
                pass
            self.root = None
        
        # Call dismiss callback
        if self.on_dismiss:
            try:
                self.on_dismiss()
            except Exception:
                pass


# Global reference to current typing indicator (only one at a time)
_current_typing_indicator: Optional[TypingIndicator] = None


def create_typing_indicator(
    parent_root: tk.Tk,
    abort_hotkey: str = "Escape",
    on_dismiss: Optional[Callable[[], None]] = None
) -> TypingIndicator:
    """Create and show a typing indicator (called on GUI thread)."""
    global _current_typing_indicator
    
    # Dismiss any existing indicator
    if _current_typing_indicator:
        _current_typing_indicator.dismiss()
    
    _current_typing_indicator = TypingIndicator(parent_root, abort_hotkey, on_dismiss)
    return _current_typing_indicator


def dismiss_typing_indicator():
    """Dismiss the current typing indicator if any."""
    global _current_typing_indicator
    
    if _current_typing_indicator:
        _current_typing_indicator.dismiss()
        _current_typing_indicator = None
