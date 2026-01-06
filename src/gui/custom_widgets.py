#!/usr/bin/env python3
"""
Custom widgets for AI Bridge GUI.
Includes ScrollableButtonList for replacing tk.Listbox with rich buttons.
"""

import tkinter as tk
from typing import Callable, Optional, Any, Dict, List

try:
    import customtkinter as ctk
    _CTK_AVAILABLE = True
except ImportError:
    _CTK_AVAILABLE = False
    ctk = None

from .themes import ThemeColors, get_ctk_button_colors, get_ctk_font

try:
    from .emoji_renderer import get_emoji_renderer, HAVE_PIL
    HAVE_EMOJI = HAVE_PIL and _CTK_AVAILABLE
except ImportError:
    HAVE_EMOJI = False
    get_emoji_renderer = None

class ScrollableButtonList(ctk.CTkScrollableFrame if _CTK_AVAILABLE else tk.Frame):
    """
    A scrollable list of buttons acting as a selector.
    Replaces tk.Listbox to allow images/emojis and modern styling.
    """
    
    def __init__(self, master, colors: ThemeColors, command: Callable[[str], None], **kwargs):
        super().__init__(master, **kwargs)
        self.colors = colors
        self.command = command
        
        self.buttons: Dict[str, Any] = {}  # id -> button
        self.selected_id: Optional[str] = None
        self.items: List[str] = [] # ordered list of IDs
        
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
    
    def add_item(self, item_id: str, text: str, icon: str = None, font_weight: str = "normal"):
        """Add an item to the list."""
        if item_id in self.buttons:
            return

        self.items.append(item_id)
        
        # Determine image
        img = None
        display_text = text
        
        if icon:
            # Try to render emoji image
            if HAVE_EMOJI:
                renderer = get_emoji_renderer()
                img = renderer.get_ctk_image(icon, size=20)
            
            # If no image (or no renderer), prepend icon to text if not already there
            if not img and icon not in text:
                display_text = f"{icon} {text}"
        
        # Determine styling
        is_selected = (item_id == self.selected_id)
        variant = "primary" if is_selected else "secondary"
        color_kwargs = get_ctk_button_colors(self.colors, variant)
        
        if _CTK_AVAILABLE:
            btn_kwargs = {
                "text": display_text,
                "anchor": "w",
                "font": get_ctk_font(14, weight=font_weight),
                "height": 38,
                "command": lambda id=item_id: self.select(id),
                **color_kwargs
            }
            if img:
                btn_kwargs["image"] = img
                btn_kwargs["compound"] = "left"
                
            btn = ctk.CTkButton(self, **btn_kwargs)
            btn.grid(row=len(self.items)-1, column=0, sticky="ew", padx=2, pady=2)
            self.buttons[item_id] = btn
        else:
            # Fallback for standard tk
            btn = tk.Button(
                self,
                text=display_text,
                anchor="w",
                command=lambda id=item_id: self.select(id),
                bg=self.colors.accent if is_selected else self.colors.surface0,
                fg="#ffffff" if is_selected else self.colors.fg,
                relief="flat",
                padx=10,
                pady=5
            )
            btn.pack(fill="x", padx=2, pady=1)
            self.buttons[item_id] = btn

    def select(self, item_id: str):
        """Select an item and trigger callback."""
        if item_id not in self.buttons:
            return
            
        old_id = self.selected_id
        if old_id == item_id:
            return # Already selected
            
        self.selected_id = item_id
        
        # Update colors
        self._update_button_colors(old_id)
        self._update_button_colors(item_id)
        
        # Trigger callback
        if self.command:
            self.command(item_id)
            
    def _update_button_colors(self, item_id: Optional[str]):
        """Update styling for a single button."""
        if not item_id or item_id not in self.buttons:
            return
            
        btn = self.buttons[item_id]
        is_selected = (item_id == self.selected_id)
        variant = "primary" if is_selected else "secondary"
        
        if _CTK_AVAILABLE:
            # Configure colors - exclude border_width as it causes flicker sometimes
            colors = get_ctk_button_colors(self.colors, variant)
            btn.configure(
                fg_color=colors["fg_color"],
                text_color=colors["text_color"],
                hover_color=colors["hover_color"]
            )
        else:
            btn.configure(
                bg=self.colors.accent if is_selected else self.colors.surface0,
                fg="#ffffff" if is_selected else self.colors.fg
            )

    def clear(self):
        """Remove all items."""
        for btn in self.buttons.values():
            btn.destroy()
        self.buttons.clear()
        self.items.clear()
        self.selected_id = None

    def get_selected(self) -> Optional[str]:
        """Get ID of currently selected item."""
        return self.selected_id
        
    def selection_clear(self):
        """Clear selection visuals."""
        old_id = self.selected_id
        self.selected_id = None
        self._update_button_colors(old_id)

    def delete(self, item_id: str):
        """Delete an item."""
        if item_id in self.buttons:
            self.buttons[item_id].destroy()
            del self.buttons[item_id]
            if item_id in self.items:
                self.items.remove(item_id)
            if self.selected_id == item_id:
                self.selected_id = None

    def size(self) -> int:
        return len(self.items)

    def update_item(self, item_id: str, text: str, icon: str = None):
        """Update an existing item's text and icon."""
        if item_id not in self.buttons:
            return
            
        btn = self.buttons[item_id]
        img = None
        display_text = text
        
        if icon:
            if HAVE_EMOJI:
                renderer = get_emoji_renderer()
                img = renderer.get_ctk_image(icon, size=20)
            if not img and icon not in text:
                display_text = f"{icon} {text}"
                
        btn.configure(text=display_text, image=img)


def upgrade_tabview_with_icons(tabview, icon_size: int = 24, font_size: int = 14):
    """
    Upgrade CTkTabview tabs with larger font and emoji images.
    Uses internal hacks to access the segmented button.
    """
    if not _CTK_AVAILABLE or not isinstance(tabview, ctk.CTkTabview):
        return

    try:
        if hasattr(tabview, "_segmented_button"):
            # Enlarge font and height (public API)
            tabview._segmented_button.configure(font=get_ctk_font(font_size, "bold"), height=42)
            
            # Add images (hack via internal dict)
            if HAVE_EMOJI:
                renderer = get_emoji_renderer()
                for value in tabview._segmented_button._value_list:
                    # Split "⚡ Actions" -> "⚡", "Actions"
                    parts = value.split(" ", 1)
                    if len(parts) >= 2:
                        emoji = parts[0]
                        text = " ".join(parts[1:])
                        # Render emoji if valid first char (simple heuristic)
                        if any(ord(c) > 127 for c in emoji):
                            img = renderer.get_ctk_image(emoji, size=icon_size)
                            if img:
                                btn = tabview._segmented_button._buttons_dict.get(value)
                                if btn:
                                    btn.configure(image=img, compound="left", text=f" {text}")
    except Exception as e:
        print(f"Error upgrading tabs: {e}")


def create_section_header(parent, text: str, colors: ThemeColors, emoji: str = None, top_padding: int = 0):
    """
    Create a section header with optional emoji support.
    Handles both explicit emoji arg or parsing emoji from start of text.
    """
    if _CTK_AVAILABLE:
        # Check for emoji at start if not explicitly provided
        label_text = text
        emoji_char = emoji
        
        if not emoji_char and " " in text:
            potential_emoji, rest = text.split(" ", 1)
            if any(ord(c) > 127 for c in potential_emoji):
                emoji_char = potential_emoji
                label_text = rest
        
        kwargs = {
            "text": label_text if emoji_char else text,
            "font": get_ctk_font(15, "bold"),
            "text_color": colors.accent
        }
        
        if emoji_char and HAVE_EMOJI:
            renderer = get_emoji_renderer()
            img = renderer.get_ctk_image(emoji_char, size=22)
            if img:
                kwargs["image"] = img
                kwargs["compound"] = "left"
                kwargs["text"] = " " + label_text
        
        # Use CTkLabel
        lbl = ctk.CTkLabel(parent, **kwargs)
        lbl.pack(anchor="w", pady=(top_padding, 12))
        return lbl
    else:
        # Fallback tk
        full_text = f"{emoji} {text}" if emoji else text
        lbl = tk.Label(parent, text=full_text, font=("Segoe UI", 11, "bold"),
                bg=colors.bg, fg=colors.accent)
        lbl.pack(anchor="w", pady=(top_padding, 10))
        return lbl


def create_emoji_button(parent, text: str, icon: str, colors: ThemeColors,
                        variant: str = "primary", width: int = 140,
                        height: int = 38, command: Callable = None,
                        font_size: int = 13, **kwargs):
    """
    Create a styled button with optional emoji icon.
    Handles rendering emoji as image (CTk) or text fallback.
    """
    if _CTK_AVAILABLE:
        img = None
        display_text = text
        
        if icon and HAVE_EMOJI:
            renderer = get_emoji_renderer()
            img = renderer.get_ctk_image(icon, size=20)
        
        if not img and icon:
            display_text = f"{icon} {text}" if text else icon
            
        button_kwargs = {
            "text": display_text,
            "font": get_ctk_font(font_size),
            "width": width,
            "height": height,
            "command": command,
            **get_ctk_button_colors(colors, variant),
            **kwargs
        }
        
        if img:
            button_kwargs["image"] = img
            button_kwargs["compound"] = "left"
            
        return ctk.CTkButton(parent, **button_kwargs)
    else:
        # Fallback for standard tk
        full_text = f"{icon} {text}" if (icon and text) else (text or icon)
        
        # Map variant to colors
        bg_color = colors.accent
        fg_color = "#ffffff"
        
        if variant == "success":
            bg_color = colors.accent_green
        elif variant == "danger":
            bg_color = colors.accent_red
        elif variant == "secondary":
            bg_color = colors.surface1
            fg_color = colors.fg
            
        btn = tk.Button(
            parent,
            text=full_text,
            command=command,
            font=("Segoe UI", 9),
            bg=bg_color,
            fg=fg_color,
            padx=10,
            pady=5
        )
        return btn
