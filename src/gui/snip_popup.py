#!/usr/bin/env python3
"""
Snip popup window for image analysis.

Displays after a successful screen capture, showing:
- Image thumbnail preview
- Action source selector (Snip actions vs TextEditTool actions)
- Custom question input
- Action buttons organized by groups

Threading Note:
    This must be created on the GUI thread via GUICoordinator.
    Uses CTkToplevel when CustomTkinter is available.
"""

import io
import logging
import tkinter as tk
from typing import Callable, Optional, Dict, List, Any

from PIL import Image, ImageTk

# Import CustomTkinter with fallback
from .platform import HAVE_CTK, ctk

# Import theme system
from .themes import (
    get_colors, ThemeColors,
    get_ctk_font, get_ctk_button_colors,
    get_ctk_frame_colors, get_ctk_entry_colors,
    sync_ctk_appearance
)

from .utils import hide_from_taskbar
from .custom_widgets import create_emoji_button
from .popups import (
    Tooltip, GroupedButtonList, CarouselButtonList,
    setup_transparent_popup, TRANSPARENCY_COLOR
)
from .screen_snip import CaptureResult


class AttachedSnipPopup:
    """
    Popup for interacting with captured screenshot.
    
    Layout:
    ┌─────────────────────────────────────────────────────────┐
    │ [×] Close                                               │
    ├─────────────────────────────────────────────────────────┤
    │ ┌───────────┐  ┌─────────────────────────────────────┐  │
    │ │   Image   │  │ Source: [Snip Actions ▼]            │  │
    │ │  Preview  │  │                                     │  │
    │ │  (thumb)  │  │ [Ask about this image........] [➤]  │  │
    │ └───────────┘  └─────────────────────────────────────┘  │
    ├─────────────────────────────────────────────────────────┤
    │ ──── Analysis ─────────────────────────────────────     │
    │ [◀] [🖼️ Describe] [📄 Extract Text] [💻 Explain Code] [▶]│
    │                    ● ○ ○                                │
    └─────────────────────────────────────────────────────────┘
    """
    
    PLACEHOLDER = "Ask about this image..."
    THUMBNAIL_MAX_SIZE = (120, 120)
    
    def __init__(
        self,
        parent_root: tk.Tk,
        capture_result: CaptureResult,
        prompts_config: Dict[str, Any],
        on_action: Callable[[str, str, Optional[str]], None],
        on_close: Optional[Callable[[], None]] = None,
        x: Optional[int] = None,
        y: Optional[int] = None
    ):
        """
        Initialize the snip popup.
        
        Args:
            parent_root: Parent Tk root (from GUICoordinator)
            capture_result: The captured image data
            prompts_config: Combined prompts config with snip_tool and optionally text_edit_tool
            on_action: Callback(source, action_key, custom_input) when action is selected
                source: "snip" or "text_edit"
                action_key: The action name (e.g., "Describe", "Proofread")
                custom_input: Custom question text (if any)
            on_close: Callback when popup is closed
            x, y: Position coordinates (optional, defaults to cursor position)
        """
        self.parent_root = parent_root
        self.capture_result = capture_result
        self.prompts_config = prompts_config
        self.on_action = on_action
        self.on_close_callback = on_close
        self.x = x
        self.y = y
        
        self.colors = get_colors()
        self.root = None
        
        # Current action source: "snip" or "text_edit"
        self.action_source = "snip"
        
        # UI references
        self.source_dropdown = None
        self.input_entry = None
        self.actions_frame = None
        self.carousel = None
        
        # Thumbnail
        self.thumbnail_photo = None
        
        self._create_window()
    
    def _create_window(self):
        """Create the popup window."""
        if HAVE_CTK:
            sync_ctk_appearance()
            self.root = ctk.CTkToplevel(self.parent_root)
        else:
            self.root = tk.Toplevel(self.parent_root)
        
        # Hide while building
        self.root.withdraw()
        
        self.root.title("Screen Snip")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        
        # Transparent corners on Windows
        setup_transparent_popup(self.root, self.colors)
        hide_from_taskbar(self.root)
        
        if HAVE_CTK:
            self._build_ctk_ui()
        else:
            self._build_tk_ui()
        
        # Position and show
        self._position_window()
        self.root.update_idletasks()
        self.root.after(10, self._show_and_focus)
    
    def _build_ctk_ui(self):
        """Build CustomTkinter UI."""
        # Main container with rounded corners
        main_frame = ctk.CTkFrame(
            self.root,
            corner_radius=12,
            fg_color=self.colors.base,
            border_color=self.colors.surface2,
            border_width=1
        )
        main_frame.pack(fill="both", expand=True, padx=1, pady=1)
        
        content = ctk.CTkFrame(main_frame, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=12, pady=12)
        
        # Top bar with close button
        top_bar = ctk.CTkFrame(content, fg_color="transparent")
        top_bar.pack(fill="x", pady=(0, 10))
        
        # Title
        ctk.CTkLabel(
            top_bar,
            text="📷 Screen Capture",
            font=get_ctk_font(size=13, weight="bold"),
            text_color=self.colors.text
        ).pack(side="left")
        
        # Close button
        close_btn = ctk.CTkButton(
            top_bar,
            text="×",
            width=28,
            height=28,
            corner_radius=6,
            fg_color="transparent",
            hover_color=self.colors.red,
            text_color=self.colors.overlay0,
            font=get_ctk_font(size=16, weight="bold"),
            command=self._close
        )
        close_btn.pack(side="right")
        
        # Image preview and input row
        preview_row = ctk.CTkFrame(content, fg_color="transparent")
        preview_row.pack(fill="x", pady=(0, 10))
        
        # Thumbnail
        thumb_frame = ctk.CTkFrame(
            preview_row,
            fg_color=self.colors.surface0,
            corner_radius=8,
            width=self.THUMBNAIL_MAX_SIZE[0] + 10,
            height=self.THUMBNAIL_MAX_SIZE[1] + 10
        )
        thumb_frame.pack(side="left", padx=(0, 12))
        thumb_frame.pack_propagate(False)
        
        self._create_thumbnail(thumb_frame)
        
        # Right side: source selector and input
        right_side = ctk.CTkFrame(preview_row, fg_color="transparent")
        right_side.pack(side="left", fill="both", expand=True)
        
        # Source selector
        source_frame = ctk.CTkFrame(right_side, fg_color="transparent")
        source_frame.pack(fill="x", pady=(0, 8))
        
        ctk.CTkLabel(
            source_frame,
            text="Actions:",
            font=get_ctk_font(size=11),
            text_color=self.colors.overlay0
        ).pack(side="left", padx=(0, 8))
        
        # Dropdown for action source
        sources = ["Snip Actions"]
        if "text_edit_tool" in self.prompts_config:
            sources.append("Text Edit Actions")
        
        self.source_var = tk.StringVar(value=sources[0])
        self.source_dropdown = ctk.CTkOptionMenu(
            source_frame,
            values=sources,
            variable=self.source_var,
            command=self._on_source_changed,
            width=160,
            height=28,
            corner_radius=6,
            fg_color=self.colors.surface0,
            button_color=self.colors.surface1,
            button_hover_color=self.colors.surface2,
            dropdown_fg_color=self.colors.surface0,
            dropdown_hover_color=self.colors.surface1,
            text_color=self.colors.text,
            font=get_ctk_font(size=11)
        )
        self.source_dropdown.pack(side="left")
        
        # Capture info
        info_text = f"{self.capture_result.width} × {self.capture_result.height} px"
        ctk.CTkLabel(
            source_frame,
            text=info_text,
            font=get_ctk_font(size=10),
            text_color=self.colors.overlay0
        ).pack(side="right")
        
        # Custom input with send button
        input_frame = ctk.CTkFrame(
            right_side,
            fg_color=self.colors.surface0,
            corner_radius=8,
            border_color=self.colors.surface2,
            border_width=1
        )
        input_frame.pack(fill="x")
        
        self.input_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text=self.PLACEHOLDER,
            font=get_ctk_font(size=12),
            height=38,
            corner_radius=0,
            fg_color="transparent",
            border_width=0,
            text_color=self.colors.text,
            placeholder_text_color=self.colors.overlay0
        )
        
        # Send button container
        send_container = ctk.CTkFrame(input_frame, width=38, height=38, fg_color="transparent")
        send_container.pack(side="right")
        send_container.pack_propagate(False)
        
        send_btn = create_emoji_button(
            send_container,
            text="",
            icon="➤",
            colors=self.colors,
            variant="primary",
            width=38,
            height=38,
            font_size=14,
            command=self._on_custom_submit
        )
        send_btn.configure(corner_radius=8)
        send_btn.pack(fill="both", expand=True)
        
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.input_entry.bind('<Return>', lambda e: self._on_custom_submit())
        
        Tooltip(send_btn, "Ask a question about this image")
        
        # Actions area
        self.actions_frame = ctk.CTkFrame(content, fg_color="transparent")
        self.actions_frame.pack(fill="both", expand=True)
        
        self._create_action_buttons()
    
    def _build_tk_ui(self):
        """Build standard Tkinter UI (fallback)."""
        self.root.configure(bg=self.colors.base)
        
        main_frame = tk.Frame(
            self.root,
            bg=self.colors.base,
            highlightbackground=self.colors.surface2,
            highlightthickness=1
        )
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        content = tk.Frame(main_frame, bg=self.colors.base)
        content.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        
        # Top bar
        top_bar = tk.Frame(content, bg=self.colors.base)
        top_bar.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(
            top_bar,
            text="📷 Screen Capture",
            font=("Arial", 12, "bold"),
            bg=self.colors.base,
            fg=self.colors.text
        ).pack(side=tk.LEFT)
        
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
        
        # Preview row
        preview_row = tk.Frame(content, bg=self.colors.base)
        preview_row.pack(fill=tk.X, pady=(0, 10))
        
        # Thumbnail
        thumb_frame = tk.Frame(
            preview_row,
            bg=self.colors.surface0,
            width=self.THUMBNAIL_MAX_SIZE[0] + 10,
            height=self.THUMBNAIL_MAX_SIZE[1] + 10,
            highlightbackground=self.colors.surface2,
            highlightthickness=1
        )
        thumb_frame.pack(side=tk.LEFT, padx=(0, 12))
        thumb_frame.pack_propagate(False)
        
        self._create_thumbnail_tk(thumb_frame)
        
        # Right side
        right_side = tk.Frame(preview_row, bg=self.colors.base)
        right_side.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Source selector (simplified for tk)
        source_frame = tk.Frame(right_side, bg=self.colors.base)
        source_frame.pack(fill=tk.X, pady=(0, 8))
        
        tk.Label(
            source_frame,
            text="Actions:",
            font=("Arial", 10),
            bg=self.colors.base,
            fg=self.colors.overlay0
        ).pack(side=tk.LEFT, padx=(0, 8))
        
        # For tk, use a simple label toggle instead of dropdown
        self.source_label = tk.Label(
            source_frame,
            text="[Snip Actions]",
            font=("Arial", 10, "bold"),
            bg=self.colors.surface0,
            fg=self.colors.text,
            padx=10,
            pady=4,
            cursor="hand2"
        )
        self.source_label.pack(side=tk.LEFT)
        self.source_label.bind('<Button-1>', self._toggle_source_tk)
        
        # Info
        info_text = f"{self.capture_result.width} × {self.capture_result.height} px"
        tk.Label(
            source_frame,
            text=info_text,
            font=("Arial", 9),
            bg=self.colors.base,
            fg=self.colors.overlay0
        ).pack(side=tk.RIGHT)
        
        # Input
        input_container = tk.Frame(
            right_side,
            bg=self.colors.surface0,
            highlightbackground=self.colors.surface2,
            highlightthickness=1
        )
        input_container.pack(fill=tk.X)
        
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
        self.input_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.input_entry.insert(0, self.PLACEHOLDER)
        self.input_entry.config(fg=self.colors.overlay0)
        
        self.input_entry.bind('<FocusIn>', self._on_input_focus_in)
        self.input_entry.bind('<FocusOut>', self._on_input_focus_out)
        self.input_entry.bind('<Return>', lambda e: self._on_custom_submit())
        
        # Send button
        send_btn = tk.Label(
            input_container,
            text="➤",
            font=("Arial", 14),
            bg=self.colors.blue,
            fg="#ffffff",
            padx=12,
            pady=8,
            cursor="hand2"
        )
        send_btn.pack(side=tk.RIGHT, fill=tk.Y)
        send_btn.bind('<Button-1>', lambda e: self._on_custom_submit())
        send_btn.bind('<Enter>', lambda e: send_btn.config(bg=self.colors.lavender))
        send_btn.bind('<Leave>', lambda e: send_btn.config(bg=self.colors.blue))
        
        # Actions area
        self.actions_frame = tk.Frame(content, bg=self.colors.base)
        self.actions_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        self._create_action_buttons()
    
    def _create_thumbnail(self, parent):
        """Create thumbnail preview (CTk version)."""
        if not self.capture_result.pil_image:
            # Create placeholder
            ctk.CTkLabel(
                parent,
                text="🖼️",
                font=get_ctk_font(size=32),
                text_color=self.colors.overlay0
            ).pack(expand=True)
            return
        
        try:
            # Create thumbnail
            thumb = self.capture_result.pil_image.copy()
            thumb.thumbnail(self.THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)
            self.thumbnail_photo = ImageTk.PhotoImage(thumb)
            
            # Display in label (use tk.Label for image display)
            label = tk.Label(parent, image=self.thumbnail_photo, bg=self.colors.surface0)
            label.pack(expand=True)
            
        except Exception as e:
            logging.error(f"[SnipPopup] Thumbnail error: {e}")
            ctk.CTkLabel(
                parent,
                text="🖼️",
                font=get_ctk_font(size=32),
                text_color=self.colors.overlay0
            ).pack(expand=True)
    
    def _create_thumbnail_tk(self, parent):
        """Create thumbnail preview (tk version)."""
        if not self.capture_result.pil_image:
            tk.Label(
                parent,
                text="🖼️",
                font=("Arial", 24),
                bg=self.colors.surface0,
                fg=self.colors.overlay0
            ).pack(expand=True)
            return
        
        try:
            thumb = self.capture_result.pil_image.copy()
            thumb.thumbnail(self.THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)
            self.thumbnail_photo = ImageTk.PhotoImage(thumb)
            
            label = tk.Label(parent, image=self.thumbnail_photo, bg=self.colors.surface0)
            label.pack(expand=True)
            
        except Exception as e:
            logging.error(f"[SnipPopup] Thumbnail error: {e}")
            tk.Label(
                parent,
                text="🖼️",
                font=("Arial", 24),
                bg=self.colors.surface0,
                fg=self.colors.overlay0
            ).pack(expand=True)
    
    def _create_action_buttons(self):
        """Create action buttons based on current source."""
        # Clear existing
        for widget in self.actions_frame.winfo_children():
            widget.destroy()
        
        # Get actions for current source
        if self.action_source == "snip":
            config = self.prompts_config.get("snip_tool", {})
        else:
            config = self.prompts_config.get("text_edit_tool", {})
        
        settings = config.get("_settings", {})
        use_groups = settings.get("popup_use_groups", True)
        
        if use_groups:
            popup_groups = settings.get("popup_groups", [])
            if popup_groups:
                groups = []
                for group_def in popup_groups:
                    group_name = group_def.get("name", "")
                    item_keys = group_def.get("items", [])
                    
                    items = []
                    for key in item_keys:
                        action = config.get(key)
                        if action and not key.startswith("_"):
                            icon = action.get("icon", "")
                            tooltip = action.get("task", "")
                            items.append((key, key, icon, tooltip))
                    
                    if items:
                        groups.append({"name": group_name, "items": items})
                
                if groups:
                    self.carousel = GroupedButtonList(
                        self.actions_frame,
                        groups=groups,
                        on_click=self._on_action_click,
                        on_group_changed=self._reposition_window
                    )
                    self.carousel.pack(fill="both" if HAVE_CTK else tk.BOTH, expand=True)
                    return
        
        # Fallback: flat carousel
        items_per_page = settings.get("popup_items_per_page", 6)
        items = []
        
        for key, action in config.items():
            if key.startswith("_"):
                continue
            if not isinstance(action, dict):
                continue
            
            icon = action.get("icon", "")
            tooltip = action.get("task", "")
            items.append((key, key, icon, tooltip))
        
        if items:
            self.carousel = CarouselButtonList(
                self.actions_frame,
                items=items,
                on_click=self._on_action_click,
                items_per_page=items_per_page
            )
            self.carousel.pack(fill="both" if HAVE_CTK else tk.BOTH, expand=True)
    
    def _on_source_changed(self, value: str):
        """Handle action source dropdown change."""
        if "Text Edit" in value:
            self.action_source = "text_edit"
        else:
            self.action_source = "snip"
        
        self._create_action_buttons()
        self._reposition_window()
    
    def _toggle_source_tk(self, event):
        """Toggle action source (tk fallback)."""
        if self.action_source == "snip" and "text_edit_tool" in self.prompts_config:
            self.action_source = "text_edit"
            self.source_label.config(text="[Text Edit Actions]")
        else:
            self.action_source = "snip"
            self.source_label.config(text="[Snip Actions]")
        
        self._create_action_buttons()
        self._reposition_window()
    
    def _on_action_click(self, action_key: str):
        """Handle action button click."""
        self._close()
        self.on_action(self.action_source, action_key, None)
    
    def _on_custom_submit(self):
        """Handle custom question submission."""
        if HAVE_CTK:
            text = self.input_entry.get().strip()
        else:
            text = self.input_var.get().strip() if hasattr(self, 'input_var') else ""
        
        if not text or text == self.PLACEHOLDER:
            return
        
        self._close()
        self.on_action(self.action_source, "_Custom", text)
    
    def _on_input_focus_in(self, event):
        """Handle input focus in (tk fallback)."""
        if self.input_entry.get() == self.PLACEHOLDER:
            self.input_entry.delete(0, tk.END)
            self.input_entry.config(fg=self.colors.text)
    
    def _on_input_focus_out(self, event):
        """Handle input focus out (tk fallback)."""
        if not self.input_entry.get():
            self.input_entry.insert(0, self.PLACEHOLDER)
            self.input_entry.config(fg=self.colors.overlay0)
    
    def _position_window(self):
        """Position the window."""
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
        
        # Ensure window stays on screen
        if x + window_width > screen_width:
            x = screen_width - window_width - 10
        if y + window_height > screen_height:
            y = screen_height - window_height - 10
        
        x = max(10, x)
        y = max(10, y)
        
        self.root.geometry(f"+{x}+{y}")
    
    def _reposition_window(self):
        """Reposition after content changes."""
        if not self.root:
            return
        
        self.root.update_idletasks()
        
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = self.root.winfo_reqwidth()
        window_height = self.root.winfo_reqheight()
        
        if x + window_width > screen_width:
            x = screen_width - window_width - 10
        if y + window_height > screen_height:
            y = screen_height - window_height - 10
        
        x = max(10, x)
        y = max(10, y)
        
        self.root.geometry(f"+{x}+{y}")
    
    def _show_and_focus(self):
        """Show window after UI is built."""
        if not self.root:
            return
        
        try:
            self.root.deiconify()
            self.root.bind('<Escape>', lambda e: self._close())
            self.root.lift()
            self.root.focus_force()
            
            if HAVE_CTK:
                self.input_entry.focus_set()
        except tk.TclError:
            pass
    
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


def create_attached_snip_popup(
    parent_root: tk.Tk,
    capture_result: CaptureResult,
    prompts_config: Dict[str, Any],
    on_action: Callable[[str, str, Optional[str]], None],
    on_close: Optional[Callable[[], None]] = None,
    x: Optional[int] = None,
    y: Optional[int] = None
) -> AttachedSnipPopup:
    """
    Create a snip popup attached to the GUI coordinator's root.
    
    Args:
        parent_root: Parent Tk root
        capture_result: Captured image data
        prompts_config: Combined prompts configuration
        on_action: Callback for action selection
        on_close: Callback when popup closes
        x, y: Position coordinates
        
    Returns:
        The created popup instance
    """
    return AttachedSnipPopup(
        parent_root, capture_result, prompts_config,
        on_action, on_close, x, y
    )