#!/usr/bin/env python3
"""
Prompt Editor Window for AI Bridge

Provides a GUI for editing text_edit_tool_options.json without opening the file directly.
Features:
- Action list with add/delete/duplicate
- Action editor (icon, prompt_type, system_prompt, task)
- Settings editor for _settings object
- Modifier and group management
- Playground for testing prompts with live preview

CustomTkinter Migration: Uses CTk widgets for modern UI.
"""

import json
import os
import sys
import time
import shutil
import threading
import base64
import tkinter as tk
from tkinter import messagebox, filedialog
from typing import Dict, Optional, List, Callable, Any
from pathlib import Path
import pyperclip

import threading

# Import CustomTkinter with fallback
try:
    import customtkinter as ctk
    _CTK_AVAILABLE = True
except ImportError:
    _CTK_AVAILABLE = False
    ctk = None


def _can_use_ctk() -> bool:
    """
    Check if CustomTkinter can be safely used.
    """
    return _CTK_AVAILABLE


# Note: For class definitions that inherit from ctk or tk, we use _CTK_AVAILABLE
# since inheritance is determined at import time. For runtime widget creation,
# call _can_use_ctk() to check both availability AND main thread.

from .themes import (
    ThemeRegistry, ThemeColors, get_colors, sync_ctk_appearance,
    get_ctk_button_colors, get_ctk_frame_colors, get_ctk_entry_colors,
    get_ctk_textbox_colors, get_ctk_combobox_colors, get_ctk_label_colors,
    get_ctk_font
)
from .core import get_next_window_id, register_window, unregister_window


# =============================================================================
# JSON Parser/Writer
# =============================================================================

OPTIONS_FILE = "text_edit_tool_options.json"


def load_options(filepath: str = OPTIONS_FILE) -> Dict:
    """
    Load and parse options JSON.
    
    Returns:
        Dict with all options, or empty dict on error
    """
    try:
        if not Path(filepath).exists():
            return {}
        
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[PromptEditor] Error loading options: {e}")
        return {}


def save_options(data: Dict, filepath: str = OPTIONS_FILE) -> bool:
    """
    Save options with proper formatting.
    Creates a backup before saving.
    
    Returns:
        True if save was successful
    """
    try:
        # Create backup
        if Path(filepath).exists():
            backup_path = filepath + ".bak"
            shutil.copy2(filepath, backup_path)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"[PromptEditor] Error saving options: {e}")
        return False


# =============================================================================
# Emoji Picker (CTk version)
# =============================================================================

COMMON_EMOJIS = [
    "💡", "🧒", "🤙", "📋", "🔑", "✏", "✨", "📝", "🔄", "💼",
    "😊", "😎", "✂", "📊", "→", "💬", "(◕‿◕)", "⚡", "❓",
    "🎨", "📖", "🔧", "⚙️", "🔍", "💾", "📁", "✅", "❌", "⭐",
    "🚀", "💪", "🎯", "📌", "🔔", "💡", "🎉", "👍", "👎", "🤔"
]


class EmojiPicker(ctk.CTkToplevel if _CTK_AVAILABLE else tk.Toplevel):
    """Simple emoji picker popup - CTk version."""
    
    def __init__(self, parent, callback: Callable[[str], None], colors: ThemeColors):
        super().__init__(parent)
        self.callback = callback
        self.colors = colors
        self.use_ctk = _can_use_ctk()
        
        self.title("Pick Icon")
        self.geometry("450x340")
        self.transient(parent)
        self.grab_set()
        
        if self.use_ctk:
            self.configure(fg_color=colors.bg)
        else:
            self.configure(bg=colors.bg)
        
        # Main frame
        main_frame = ctk.CTkFrame(self, fg_color=colors.bg) if self.use_ctk else tk.Frame(self, bg=colors.bg)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Grid of emojis
        emoji_frame = ctk.CTkFrame(main_frame, fg_color=colors.bg) if self.use_ctk else tk.Frame(main_frame, bg=colors.bg)
        emoji_frame.pack(fill="both", expand=True)
        
        cols = 10
        for i, emoji in enumerate(COMMON_EMOJIS):
            row = i // cols
            col = i % cols
            if self.use_ctk:
                btn = ctk.CTkButton(
                    emoji_frame,
                    text=emoji,
                    font=get_ctk_font(18),
                    width=40,
                    height=36,
                    corner_radius=6,
                    **get_ctk_button_colors(colors, "secondary"),
                    command=lambda em=emoji: self._select(em)
                )
            else:
                btn = tk.Label(
                    emoji_frame,
                    text=emoji,
                    font=("Segoe UI", 18),
                    bg=colors.surface0,
                    fg=colors.fg,
                    width=3,
                    height=1,
                    cursor="hand2"
                )
                btn.bind('<Button-1>', lambda e, em=emoji: self._select(em))
            btn.grid(row=row, column=col, padx=3, pady=3)
        
        # Custom entry section
        custom_frame = ctk.CTkFrame(main_frame, fg_color=colors.bg) if self.use_ctk else tk.Frame(main_frame, bg=colors.bg)
        custom_frame.pack(fill="x", pady=(15, 0))
        
        if self.use_ctk:
            ctk.CTkLabel(
                custom_frame,
                text="Custom:",
                font=get_ctk_font(12),
                **get_ctk_label_colors(colors)
            ).pack(side="left")
            
            self.custom_entry = ctk.CTkEntry(
                custom_frame,
                width=100,
                font=get_ctk_font(14),
                **get_ctk_entry_colors(colors)
            )
            self.custom_entry.pack(side="left", padx=10)
            
            ctk.CTkButton(
                custom_frame,
                text="Use",
                font=get_ctk_font(11),
                width=60,
                **get_ctk_button_colors(colors, "primary"),
                command=self._use_custom
            ).pack(side="left")
        else:
            tk.Label(custom_frame, text="Custom:", font=("Segoe UI", 11),
                    bg=colors.bg, fg=colors.fg).pack(side="left")
            self.custom_entry = tk.Entry(custom_frame, width=12, font=("Segoe UI", 14),
                                        bg=colors.input_bg, fg=colors.fg)
            self.custom_entry.pack(side="left", padx=8)
            tk.Button(custom_frame, text="Use", command=self._use_custom,
                     bg=colors.accent, fg="#ffffff").pack(side="left")
    
    def _select(self, emoji: str):
        """Select an emoji."""
        self.callback(emoji)
        self.destroy()
    
    def _use_custom(self):
        """Use custom text as icon."""
        text = self.custom_entry.get().strip()
        if text:
            self.callback(text)
            self.destroy()


# =============================================================================
# Themed Input Dialog (CTk version)
# =============================================================================

class ThemedInputDialog(ctk.CTkToplevel if _CTK_AVAILABLE else tk.Toplevel):
    """Themed dialog for getting text input from user."""
    
    def __init__(self, parent, title: str, prompt: str, colors: ThemeColors):
        super().__init__(parent)
        self.colors = colors
        self.result = None
        self.use_ctk = _can_use_ctk()
        
        self.title(title)
        self.geometry("400x180")
        self.transient(parent)
        self.grab_set()
        
        if self.use_ctk:
            self.configure(fg_color=colors.bg)
        else:
            self.configure(bg=colors.bg)
        
        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 200
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 90
        self.geometry(f"+{x}+{y}")
        
        # Main frame
        main_frame = ctk.CTkFrame(self, fg_color=colors.bg) if self.use_ctk else tk.Frame(self, bg=colors.bg)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Prompt label
        if self.use_ctk:
            ctk.CTkLabel(
                main_frame,
                text=prompt,
                font=get_ctk_font(12),
                **get_ctk_label_colors(colors)
            ).pack(anchor="w", pady=(0, 10))
            
            self.entry = ctk.CTkEntry(
                main_frame,
                width=360,
                height=36,
                font=get_ctk_font(12),
                **get_ctk_entry_colors(colors)
            )
            self.entry.pack(fill="x", pady=(0, 15))
        else:
            tk.Label(main_frame, text=prompt, font=("Segoe UI", 11),
                    bg=colors.bg, fg=colors.fg).pack(anchor="w", pady=(0, 10))
            self.entry = tk.Entry(main_frame, font=("Segoe UI", 11),
                                 bg=colors.input_bg, fg=colors.fg, width=40)
            self.entry.pack(fill="x", pady=(0, 15), ipady=6)
        
        self.entry.focus_set()
        
        # Buttons
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent") if self.use_ctk else tk.Frame(main_frame, bg=colors.bg)
        btn_frame.pack()
        
        if self.use_ctk:
            ctk.CTkButton(
                btn_frame,
                text="OK",
                font=get_ctk_font(11),
                width=80,
                **get_ctk_button_colors(colors, "primary"),
                command=self._ok
            ).pack(side="left", padx=5)
            
            ctk.CTkButton(
                btn_frame,
                text="Cancel",
                font=get_ctk_font(11),
                width=80,
                **get_ctk_button_colors(colors, "secondary"),
                command=self._cancel
            ).pack(side="left", padx=5)
        else:
            tk.Button(btn_frame, text="OK", command=self._ok,
                     bg=colors.accent, fg="#ffffff").pack(side="left", padx=5)
            tk.Button(btn_frame, text="Cancel", command=self._cancel,
                     bg=colors.surface1, fg=colors.fg).pack(side="left", padx=5)
        
        # Bindings
        self.entry.bind('<Return>', lambda e: self._ok())
        self.bind('<Escape>', lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
    
    def _ok(self):
        """Accept the input."""
        self.result = self.entry.get().strip()
        self.destroy()
    
    def _cancel(self):
        """Cancel the dialog."""
        self.result = None
        self.destroy()


def ask_themed_string(parent, title: str, prompt: str, colors: ThemeColors) -> Optional[str]:
    """Show a themed input dialog and return the result."""
    dialog = ThemedInputDialog(parent, title, prompt, colors)
    parent.wait_window(dialog)
    return dialog.result


# =============================================================================
# Prompt Editor Window (CTk version)
# =============================================================================

class PromptEditorWindow:
    """
    Standalone prompt editor window using CustomTkinter.
    """
    
    def __init__(self, master=None):
        self.window_id = get_next_window_id()
        self.window_tag = f"prompt_editor_{self.window_id}"
        
        self.master = master
        self.colors = get_colors()
        self.root = None  # type: ignore
        self._destroyed = False
        
        # Data
        self.options_data: Dict = {}
        self.current_action: Optional[str] = None
        
        # Playground image data
        self.playground_image_base64: Optional[str] = None
        self.playground_image_mime: Optional[str] = None
        self.playground_image_name: Optional[str] = None
        
        # Widget references
        self.action_listbox = None
        self.editor_widgets: Dict[str, Any] = {}
        
        # Determine if we can use CTk (must be in main thread)
        self.use_ctk = _can_use_ctk()
    
    def show(self):
        """Create and show the prompt editor window."""
        # Only sync CTk if we can use it
        if self.use_ctk:
            sync_ctk_appearance()
        
        # Load current options
        self.options_data = load_options()
        
        if self.master:
            # Attached mode - child window
            if self.use_ctk:
                self.root = ctk.CTkToplevel(self.master)
                self.root.configure(fg_color=self.colors.bg)
            else:
                self.root = tk.Toplevel(self.master)
                self.root.configure(bg=self.colors.bg)
        else:
            # Standalone mode - root window
            if self.use_ctk:
                self.root = ctk.CTk()
                self.root.configure(fg_color=self.colors.bg)
            else:
                self.root = tk.Tk()
                self.root.configure(bg=self.colors.bg)
        
        self.root.title("AI Bridge Prompt Editor")
        self.root.geometry("1200x850")
        self.root.minsize(1000, 650)
        
        # Set icon - use repeated after() calls to override CTk's default icon
        self._icon_path = Path(__file__).parent.parent.parent / "icon.ico"
        def _set_icon():
            try:
                if self._icon_path.exists() and self.root and not self._destroyed:
                    self.root.iconbitmap(str(self._icon_path))
            except Exception:
                pass
        
        # Apply icon multiple times to override CTk default
        self.root.after(50, _set_icon)
        self.root.after(150, _set_icon)
        self.root.after(300, _set_icon)
        
        # Position window
        offset = (self.window_id % 3) * 30
        self.root.geometry(f"+{80 + offset}+{80 + offset}")
        
        # Main container
        main_container = ctk.CTkFrame(self.root, fg_color=self.colors.bg) if self.use_ctk else tk.Frame(self.root, bg=self.colors.bg)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Title bar
        self._create_title_bar(main_container)
        
        # Main content with tabview
        self._create_main_content(main_container)
        
        # Button bar
        self._create_button_bar(main_container)
        
        # Register and bind
        register_window(self.window_tag)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.bind('<Escape>', lambda e: self._close())
        
        # Focus
        self.root.lift()
        self.root.focus_force()
        
        # Event loop (only if standalone)
        if not self.master:
            self._run_event_loop()
    
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
    
    def _create_title_bar(self, parent):
        """Create the title bar."""
        title_frame = ctk.CTkFrame(parent, fg_color="transparent") if self.use_ctk else tk.Frame(parent, bg=self.colors.bg)
        title_frame.pack(fill="x", pady=(0, 15))
        
        if self.use_ctk:
            ctk.CTkLabel(
                title_frame,
                text="✏️ Prompt Editor",
                font=get_ctk_font(24, "bold"),
                **get_ctk_label_colors(self.colors)
            ).pack(side="left")
            
            ctk.CTkLabel(
                title_frame,
                text="Edit text_edit_tool_options.json",
                font=get_ctk_font(14),
                **get_ctk_label_colors(self.colors, muted=True)
            ).pack(side="left", padx=(20, 0))
        else:
            tk.Label(title_frame, text="✏️ Prompt Editor",
                    font=("Segoe UI", 16, "bold"),
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            tk.Label(title_frame, text="Edit text_edit_tool_options.json",
                    font=("Segoe UI", 10),
                    bg=self.colors.bg, fg=self.colors.blockquote).pack(side="left", padx=(15, 0))
    
    def _create_main_content(self, parent):
        """Create the main content area with tabview."""
        if self.use_ctk:
            self.tabview = ctk.CTkTabview(
                parent,
                fg_color=self.colors.bg,
                segmented_button_fg_color=self.colors.surface0,
                segmented_button_selected_color=self.colors.accent,
                segmented_button_selected_hover_color=self.colors.lavender,
                segmented_button_unselected_color=self.colors.surface0,
                segmented_button_unselected_hover_color=self.colors.surface1,
                text_color=self.colors.fg,
                corner_radius=8
            )
            self.tabview.pack(fill="both", expand=True, pady=(0, 10))
            
            # Create tabs
            self.tabview.add("Actions")
            self.tabview.add("Settings")
            self.tabview.add("Modifiers")
            self.tabview.add("Groups")
            self.tabview.add("🧪 Playground")
            
            self._create_actions_tab(self.tabview.tab("Actions"))
            self._create_settings_tab(self.tabview.tab("Settings"))
            self._create_modifiers_tab(self.tabview.tab("Modifiers"))
            self._create_groups_tab(self.tabview.tab("Groups"))
            self._create_playground_tab(self.tabview.tab("🧪 Playground"))
        else:
            # Fallback to ttk.Notebook
            from tkinter import ttk
            style = ttk.Style(self.root)
            style.theme_use('clam')
            self.tabview = ttk.Notebook(parent)
            self.tabview.pack(fill="both", expand=True, pady=(0, 10))
            
            actions_frame = tk.Frame(self.tabview, bg=self.colors.bg)
            settings_frame = tk.Frame(self.tabview, bg=self.colors.bg)
            modifiers_frame = tk.Frame(self.tabview, bg=self.colors.bg)
            groups_frame = tk.Frame(self.tabview, bg=self.colors.bg)
            playground_frame = tk.Frame(self.tabview, bg=self.colors.bg)
            
            self.tabview.add(actions_frame, text="Actions")
            self.tabview.add(settings_frame, text="Settings")
            self.tabview.add(modifiers_frame, text="Modifiers")
            self.tabview.add(groups_frame, text="Groups")
            self.tabview.add(playground_frame, text="🧪 Playground")
            
            self._create_actions_tab(actions_frame)
            self._create_settings_tab(settings_frame)
            self._create_modifiers_tab(modifiers_frame)
            self._create_groups_tab(groups_frame)
            self._create_playground_tab(playground_frame)
    
    def _create_actions_tab(self, frame):
        """Create the Actions editing tab."""
        # Container with left/right panes
        container = ctk.CTkFrame(frame, fg_color="transparent") if self.use_ctk else tk.Frame(frame, bg=self.colors.bg)
        container.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Left panel: action list (fixed width)
        left_panel = ctk.CTkFrame(container, fg_color="transparent", width=260) if self.use_ctk else tk.Frame(container, bg=self.colors.bg, width=260)
        left_panel.pack(side="left", fill="y", padx=(0, 15))
        left_panel.pack_propagate(False)
        
        if self.use_ctk:
            ctk.CTkLabel(
                left_panel,
                text="Actions",
                font=get_ctk_font(14, "bold"),
                text_color=self.colors.accent
            ).pack(anchor="w", pady=(0, 12))
        else:
            tk.Label(left_panel, text="Actions", font=("Segoe UI", 11, "bold"),
                    bg=self.colors.bg, fg=self.colors.accent).pack(anchor="w", pady=(0, 10))
        
        # Listbox (using tk.Listbox wrapped in frame for scrolling)
        list_container = ctk.CTkFrame(left_panel, fg_color=self.colors.input_bg, corner_radius=8) if self.use_ctk else tk.Frame(left_panel, bg=self.colors.input_bg)
        list_container.pack(fill="both", expand=True)
        
        self.action_listbox = tk.Listbox(
            list_container,
            font=("Segoe UI", 12),
            bg=self.colors.input_bg,
            fg=self.colors.fg,
            selectbackground=self.colors.accent,
            selectforeground="#ffffff",
            relief="flat",
            highlightthickness=0,
            borderwidth=0
        )
        self.action_listbox.pack(fill="both", expand=True, padx=4, pady=4)
        
        # Populate action list
        for name in sorted(self.options_data.keys()):
            if name == "_settings":
                continue
            icon = self.options_data[name].get("icon", "")
            self.action_listbox.insert("end", f"{icon} {name}")
        
        self.action_listbox.bind('<<ListboxSelect>>', self._on_action_select)
        
        # Action buttons
        btn_frame = ctk.CTkFrame(left_panel, fg_color="transparent") if self.use_ctk else tk.Frame(left_panel, bg=self.colors.bg)
        btn_frame.pack(fill="x", pady=(12, 0))
        
        if self.use_ctk:
            ctk.CTkButton(
                btn_frame, text="➕ Add", font=get_ctk_font(13),
                width=80, height=34, corner_radius=6,
                **get_ctk_button_colors(self.colors, "success"),
                command=self._add_action
            ).pack(side="left", padx=3)
            
            ctk.CTkButton(
                btn_frame, text="📋", font=get_ctk_font(13),
                width=40, height=34, corner_radius=6,
                **get_ctk_button_colors(self.colors, "secondary"),
                command=self._duplicate_action
            ).pack(side="left", padx=3)
            
            ctk.CTkButton(
                btn_frame, text="🗑️", font=get_ctk_font(13),
                width=40, height=34, corner_radius=6,
                **get_ctk_button_colors(self.colors, "danger"),
                command=self._delete_action
            ).pack(side="left", padx=3)
        else:
            tk.Button(btn_frame, text="➕ Add", font=("Segoe UI", 9),
                     bg=self.colors.accent_green, fg="#ffffff",
                     command=self._add_action).pack(side="left", padx=2)
            tk.Button(btn_frame, text="📋", font=("Segoe UI", 9),
                     bg=self.colors.surface1, fg=self.colors.fg,
                     command=self._duplicate_action).pack(side="left", padx=2)
            tk.Button(btn_frame, text="🗑️", font=("Segoe UI", 9),
                     bg=self.colors.accent_red, fg="#ffffff",
                     command=self._delete_action).pack(side="left", padx=2)
        
        # Right panel: action editor
        right_panel = ctk.CTkFrame(container, fg_color="transparent") if self.use_ctk else tk.Frame(container, bg=self.colors.bg)
        right_panel.pack(side="left", fill="both", expand=True)
        
        if self.use_ctk:
            ctk.CTkLabel(
                right_panel,
                text="Edit Action",
                font=get_ctk_font(14, "bold"),
                text_color=self.colors.accent
            ).pack(anchor="w", pady=(0, 12))
        else:
            tk.Label(right_panel, text="Edit Action", font=("Segoe UI", 11, "bold"),
                    bg=self.colors.bg, fg=self.colors.accent).pack(anchor="w", pady=(0, 10))
        
        # Editor form in scrollable frame
        if self.use_ctk:
            editor_scroll = ctk.CTkScrollableFrame(right_panel, fg_color="transparent")
        else:
            editor_scroll = tk.Frame(right_panel, bg=self.colors.bg)
        editor_scroll.pack(fill="both", expand=True)
        
        # Action name (read-only label)
        row_frame = ctk.CTkFrame(editor_scroll, fg_color="transparent") if self.use_ctk else tk.Frame(editor_scroll, bg=self.colors.bg)
        row_frame.pack(fill="x", pady=8)
        
        if self.use_ctk:
            ctk.CTkLabel(row_frame, text="Name:", font=get_ctk_font(13), width=120, anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(side="left")
            self.editor_widgets["name"] = ctk.CTkLabel(
                row_frame, text="(select an action)", font=get_ctk_font(13, "bold"),
                **get_ctk_label_colors(self.colors)
            )
        else:
            tk.Label(row_frame, text="Name:", font=("Segoe UI", 10), width=12, anchor="w",
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            self.editor_widgets["name"] = tk.Label(row_frame, text="(select an action)",
                                                   font=("Segoe UI", 10, "bold"),
                                                   bg=self.colors.bg, fg=self.colors.fg)
        self.editor_widgets["name"].pack(side="left", padx=(10, 0))
        
        # Icon field
        row_frame = ctk.CTkFrame(editor_scroll, fg_color="transparent") if self.use_ctk else tk.Frame(editor_scroll, bg=self.colors.bg)
        row_frame.pack(fill="x", pady=8)
        
        if self.use_ctk:
            ctk.CTkLabel(row_frame, text="Icon:", font=get_ctk_font(13), width=120, anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(side="left")
            self.editor_widgets["icon_var"] = tk.StringVar(master=self.root)
            self.editor_widgets["icon_entry"] = ctk.CTkEntry(
                row_frame, textvariable=self.editor_widgets["icon_var"],
                font=get_ctk_font(16), width=70, height=34, **get_ctk_entry_colors(self.colors)
            )
            self.editor_widgets["icon_entry"].pack(side="left", padx=(12, 8))
            ctk.CTkButton(
                row_frame, text="Pick...", font=get_ctk_font(13),
                width=80, height=34, **get_ctk_button_colors(self.colors, "secondary"),
                command=self._pick_icon
            ).pack(side="left")
        else:
            tk.Label(row_frame, text="Icon:", font=("Segoe UI", 10), width=12, anchor="w",
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            self.editor_widgets["icon_var"] = tk.StringVar(master=self.root)
            self.editor_widgets["icon_entry"] = tk.Entry(
                row_frame, textvariable=self.editor_widgets["icon_var"],
                font=("Segoe UI", 12), width=5, bg=self.colors.input_bg, fg=self.colors.fg
            )
            self.editor_widgets["icon_entry"].pack(side="left", padx=(10, 5))
            tk.Button(row_frame, text="Pick...", font=("Segoe UI", 9),
                     bg=self.colors.surface1, fg=self.colors.fg,
                     command=self._pick_icon).pack(side="left")
        
        # Prompt type dropdown
        row_frame = ctk.CTkFrame(editor_scroll, fg_color="transparent") if self.use_ctk else tk.Frame(editor_scroll, bg=self.colors.bg)
        row_frame.pack(fill="x", pady=8)
        
        if self.use_ctk:
            ctk.CTkLabel(row_frame, text="Type:", font=get_ctk_font(13), width=120, anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(side="left")
            self.editor_widgets["prompt_type_var"] = tk.StringVar(master=self.root, value="edit")
            self.editor_widgets["prompt_type"] = ctk.CTkComboBox(
                row_frame, variable=self.editor_widgets["prompt_type_var"],
                values=["edit", "general"], width=180, height=34, state="readonly",
                font=get_ctk_font(13), **get_ctk_combobox_colors(self.colors)
            )
            self.editor_widgets["prompt_type"].pack(side="left", padx=(12, 0))
        else:
            from tkinter import ttk
            tk.Label(row_frame, text="Type:", font=("Segoe UI", 10), width=12, anchor="w",
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            self.editor_widgets["prompt_type_var"] = tk.StringVar(master=self.root, value="edit")
            self.editor_widgets["prompt_type"] = ttk.Combobox(
                row_frame, textvariable=self.editor_widgets["prompt_type_var"],
                values=["edit", "general"], state="readonly", width=15
            )
            self.editor_widgets["prompt_type"].pack(side="left", padx=(10, 0))
        
        # System prompt (multiline)
        row_frame = ctk.CTkFrame(editor_scroll, fg_color="transparent") if self.use_ctk else tk.Frame(editor_scroll, bg=self.colors.bg)
        row_frame.pack(fill="x", pady=8)
        
        if self.use_ctk:
            ctk.CTkLabel(row_frame, text="System Prompt:", font=get_ctk_font(13), anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(anchor="w")
            self.editor_widgets["system_prompt"] = ctk.CTkTextbox(
                row_frame, height=140, font=get_ctk_font(12),
                **get_ctk_textbox_colors(self.colors)
            )
            self.editor_widgets["system_prompt"].pack(fill="x", pady=(8, 0))
        else:
            tk.Label(row_frame, text="System Prompt:", font=("Segoe UI", 10),
                    bg=self.colors.bg, fg=self.colors.fg).pack(anchor="w")
            self.editor_widgets["system_prompt"] = tk.Text(
                row_frame, font=("Consolas", 10), height=6,
                bg=self.colors.input_bg, fg=self.colors.fg, wrap="word"
            )
            self.editor_widgets["system_prompt"].pack(fill="x", pady=(5, 0))
        
        # Task field
        row_frame = ctk.CTkFrame(editor_scroll, fg_color="transparent") if self.use_ctk else tk.Frame(editor_scroll, bg=self.colors.bg)
        row_frame.pack(fill="x", pady=8)
        
        if self.use_ctk:
            ctk.CTkLabel(row_frame, text="Task:", font=get_ctk_font(13), width=120, anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(side="left")
            self.editor_widgets["task_var"] = tk.StringVar(master=self.root)
            self.editor_widgets["task"] = ctk.CTkEntry(
                row_frame, textvariable=self.editor_widgets["task_var"],
                font=get_ctk_font(13), height=34, **get_ctk_entry_colors(self.colors)
            )
            self.editor_widgets["task"].pack(side="left", fill="x", expand=True, padx=(12, 0))
        else:
            tk.Label(row_frame, text="Task:", font=("Segoe UI", 10), width=12, anchor="w",
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            self.editor_widgets["task_var"] = tk.StringVar(master=self.root)
            self.editor_widgets["task"] = tk.Entry(
                row_frame, textvariable=self.editor_widgets["task_var"],
                font=("Segoe UI", 10), bg=self.colors.input_bg, fg=self.colors.fg
            )
            self.editor_widgets["task"].pack(side="left", fill="x", expand=True, padx=(10, 0))
        
        # Show in chat checkbox
        row_frame = ctk.CTkFrame(editor_scroll, fg_color="transparent") if self.use_ctk else tk.Frame(editor_scroll, bg=self.colors.bg)
        row_frame.pack(fill="x", pady=10)
        
        self.editor_widgets["show_chat_var"] = tk.BooleanVar(master=self.root)
        if self.use_ctk:
            self.editor_widgets["show_chat"] = ctk.CTkCheckBox(
                row_frame, text="Show response in chat window instead of replacing text",
                variable=self.editor_widgets["show_chat_var"],
                font=get_ctk_font(13), text_color=self.colors.fg,
                fg_color=self.colors.accent, hover_color=self.colors.lavender
            )
        else:
            self.editor_widgets["show_chat"] = tk.Checkbutton(
                row_frame, text="Show response in chat window instead of replacing text",
                variable=self.editor_widgets["show_chat_var"],
                font=("Segoe UI", 10), bg=self.colors.bg, fg=self.colors.fg,
                selectcolor=self.colors.input_bg
            )
        self.editor_widgets["show_chat"].pack(anchor="w")
        
        # Save action button
        btn_frame = ctk.CTkFrame(editor_scroll, fg_color="transparent") if self.use_ctk else tk.Frame(editor_scroll, bg=self.colors.bg)
        btn_frame.pack(fill="x", pady=(18, 0))
        
        if self.use_ctk:
            ctk.CTkButton(
                btn_frame, text="💾 Save Action", font=get_ctk_font(14),
                width=150, height=40, **get_ctk_button_colors(self.colors, "success"),
                command=self._save_current_action
            ).pack(side="left")
            
            self.editor_widgets["save_status"] = ctk.CTkLabel(
                btn_frame, text="", font=get_ctk_font(12),
                text_color=self.colors.accent_green
            )
        else:
            tk.Button(btn_frame, text="💾 Save Action", font=("Segoe UI", 10),
                     bg=self.colors.accent_green, fg="#ffffff",
                     command=self._save_current_action).pack(side="left")
            self.editor_widgets["save_status"] = tk.Label(
                btn_frame, text="", font=("Segoe UI", 9),
                bg=self.colors.bg, fg=self.colors.accent_green
            )
        self.editor_widgets["save_status"].pack(side="left", padx=15)
    
    def _create_settings_tab(self, frame):
        """Create the Settings tab for _settings object."""
        if self.use_ctk:
            scroll_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        else:
            scroll_frame = tk.Frame(frame, bg=self.colors.bg)
        scroll_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        settings = self.options_data.get("_settings", {})
        self.settings_widgets = {}
        
        # Section: Global Settings
        if self.use_ctk:
            ctk.CTkLabel(
                scroll_frame, text="Global Settings", font=get_ctk_font(15, "bold"),
                text_color=self.colors.accent
            ).pack(anchor="w", pady=(0, 12))
        else:
            tk.Label(scroll_frame, text="Global Settings", font=("Segoe UI", 11, "bold"),
                    bg=self.colors.bg, fg=self.colors.accent).pack(anchor="w", pady=(0, 10))
        
        # Text fields from settings
        text_fields = [
            ("chat_system_instruction", "Chat System Instruction", True),
            ("chat_window_system_instruction", "Chat Window System Instruction", True),
            ("base_output_rules", "Base Output Rules", True),
            ("base_output_rules_general", "Base Output Rules (General)", True),
            ("text_delimiter", "Text Delimiter", False),
            ("text_delimiter_close", "Text Delimiter Close", False),
            ("custom_task_template", "Custom Task Template", False),
            ("ask_task_template", "Ask Task Template", False),
        ]
        
        for key, label, multiline in text_fields:
            row = ctk.CTkFrame(scroll_frame, fg_color="transparent") if self.use_ctk else tk.Frame(scroll_frame, bg=self.colors.bg)
            row.pack(fill="x", pady=8)
            
            if self.use_ctk:
                ctk.CTkLabel(row, text=f"{label}:", font=get_ctk_font(12),
                            **get_ctk_label_colors(self.colors)).pack(anchor="w")
            else:
                tk.Label(row, text=f"{label}:", font=("Segoe UI", 10),
                        bg=self.colors.bg, fg=self.colors.fg).pack(anchor="w")
            
            if multiline:
                if self.use_ctk:
                    widget = ctk.CTkTextbox(row, height=100, font=get_ctk_font(12),
                                           **get_ctk_textbox_colors(self.colors))
                else:
                    widget = tk.Text(row, height=4, font=("Consolas", 9),
                                    bg=self.colors.input_bg, fg=self.colors.fg, wrap="word")
                widget.pack(fill="x", pady=(2, 0))
                if self.use_ctk:
                    widget.insert("0.0", settings.get(key, ""))
                else:
                    widget.insert("1.0", settings.get(key, ""))
                self.settings_widgets[key] = ("text", widget)
            else:
                var = tk.StringVar(master=scroll_frame, value=settings.get(key, ""))
                if self.use_ctk:
                    widget = ctk.CTkEntry(row, textvariable=var, font=get_ctk_font(12), height=34,
                                         **get_ctk_entry_colors(self.colors))
                else:
                    widget = tk.Entry(row, textvariable=var, font=("Segoe UI", 10),
                                     bg=self.colors.input_bg, fg=self.colors.fg)
                widget.pack(fill="x", pady=(2, 0))
                self.settings_widgets[key] = ("entry", var)
        
        # Section: Popup Settings
        if self.use_ctk:
            ctk.CTkLabel(
                scroll_frame, text="Popup Settings", font=get_ctk_font(15, "bold"),
                text_color=self.colors.accent
            ).pack(anchor="w", pady=(25, 12))
        else:
            tk.Label(scroll_frame, text="Popup Settings", font=("Segoe UI", 11, "bold"),
                    bg=self.colors.bg, fg=self.colors.accent).pack(anchor="w", pady=(20, 10))
        
        # Items per page
        row = ctk.CTkFrame(scroll_frame, fg_color="transparent") if self.use_ctk else tk.Frame(scroll_frame, bg=self.colors.bg)
        row.pack(fill="x", pady=8)
        
        if self.use_ctk:
            ctk.CTkLabel(row, text="Items per page:", font=get_ctk_font(13),
                        **get_ctk_label_colors(self.colors)).pack(side="left")
        else:
            tk.Label(row, text="Items per page:", font=("Segoe UI", 10),
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
        
        items_var = tk.IntVar(master=scroll_frame, value=settings.get("popup_items_per_page", 6))
        if self.use_ctk:
            items_entry = ctk.CTkEntry(row, textvariable=items_var, width=100, height=34, font=get_ctk_font(13),
                                      **get_ctk_entry_colors(self.colors))
        else:
            from tkinter import ttk
            items_entry = ttk.Spinbox(row, textvariable=items_var, from_=3, to=20, width=10)
        items_entry.pack(side="left", padx=(12, 18))
        
        if self.use_ctk:
            ctk.CTkLabel(row, text="(Only applies when 'Use groups' is OFF)", font=get_ctk_font(11),
                        **get_ctk_label_colors(self.colors, muted=True)).pack(side="left")
        else:
            tk.Label(row, text="(Only applies when 'Use groups' is OFF)", font=("Segoe UI", 9),
                    bg=self.colors.bg, fg=self.colors.blockquote).pack(side="left")
        
        self.settings_widgets["popup_items_per_page"] = ("int", items_var)
        
        # Use groups toggle
        row = ctk.CTkFrame(scroll_frame, fg_color="transparent") if self.use_ctk else tk.Frame(scroll_frame, bg=self.colors.bg)
        row.pack(fill="x", pady=10)
        
        groups_var = tk.BooleanVar(master=scroll_frame, value=settings.get("popup_use_groups", True))
        if self.use_ctk:
            ctk.CTkSwitch(
                row, text="Use groups for popup organization",
                variable=groups_var, font=get_ctk_font(13),
                fg_color=self.colors.surface2,
                progress_color=self.colors.accent,
                button_color="#ffffff",
                button_hover_color="#f0f0f0"
            ).pack(anchor="w")
        else:
            tk.Checkbutton(row, text="Use groups for popup organization",
                          variable=groups_var, font=("Segoe UI", 10),
                          bg=self.colors.bg, fg=self.colors.fg,
                          selectcolor=self.colors.input_bg).pack(anchor="w")
        
        self.settings_widgets["popup_use_groups"] = ("bool", groups_var)
    
    def _create_modifiers_tab(self, frame):
        """Create the Modifiers editing tab."""
        container = ctk.CTkFrame(frame, fg_color="transparent") if self.use_ctk else tk.Frame(frame, bg=self.colors.bg)
        container.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Left panel: modifier list
        left_panel = ctk.CTkFrame(container, fg_color="transparent", width=260) if self.use_ctk else tk.Frame(container, bg=self.colors.bg, width=260)
        left_panel.pack(side="left", fill="y", padx=(0, 15))
        left_panel.pack_propagate(False)
        
        if self.use_ctk:
            ctk.CTkLabel(left_panel, text="Modifiers", font=get_ctk_font(14, "bold"),
                        text_color=self.colors.accent).pack(anchor="w", pady=(0, 12))
        else:
            tk.Label(left_panel, text="Modifiers", font=("Segoe UI", 11, "bold"),
                    bg=self.colors.bg, fg=self.colors.accent).pack(anchor="w", pady=(0, 10))
        
        list_container = ctk.CTkFrame(left_panel, fg_color=self.colors.input_bg, corner_radius=8) if self.use_ctk else tk.Frame(left_panel, bg=self.colors.input_bg)
        list_container.pack(fill="both", expand=True)
        
        self.modifier_listbox = tk.Listbox(
            list_container, font=("Segoe UI", 12),
            bg=self.colors.input_bg, fg=self.colors.fg,
            selectbackground=self.colors.accent, selectforeground="#ffffff",
            relief="flat", highlightthickness=0, borderwidth=0
        )
        self.modifier_listbox.pack(fill="both", expand=True, padx=4, pady=4)
        
        # Populate modifiers
        settings = self.options_data.get("_settings", {})
        modifiers = settings.get("modifiers", [])
        for mod in modifiers:
            self.modifier_listbox.insert("end", f"{mod.get('icon', '')} {mod.get('label', mod.get('key', ''))}")
        
        self.modifier_listbox.bind('<<ListboxSelect>>', self._on_modifier_select)
        
        # Buttons
        btn_frame = ctk.CTkFrame(left_panel, fg_color="transparent") if self.use_ctk else tk.Frame(left_panel, bg=self.colors.bg)
        btn_frame.pack(fill="x", pady=(12, 0))
        
        if self.use_ctk:
            ctk.CTkButton(btn_frame, text="➕ Add", font=get_ctk_font(13),
                         width=80, height=34, **get_ctk_button_colors(self.colors, "success"),
                         command=self._add_modifier).pack(side="left", padx=3)
            ctk.CTkButton(btn_frame, text="🗑️", font=get_ctk_font(13),
                         width=40, height=34, **get_ctk_button_colors(self.colors, "danger"),
                         command=self._delete_modifier).pack(side="left", padx=3)
        else:
            tk.Button(btn_frame, text="➕ Add", font=("Segoe UI", 9),
                     bg=self.colors.accent_green, fg="#ffffff",
                     command=self._add_modifier).pack(side="left", padx=2)
            tk.Button(btn_frame, text="🗑️", font=("Segoe UI", 9),
                     bg=self.colors.accent_red, fg="#ffffff",
                     command=self._delete_modifier).pack(side="left", padx=2)
        
        # Right panel: modifier editor
        right_panel = ctk.CTkFrame(container, fg_color="transparent") if self.use_ctk else tk.Frame(container, bg=self.colors.bg)
        right_panel.pack(side="left", fill="both", expand=True)
        
        if self.use_ctk:
            ctk.CTkLabel(right_panel, text="Edit Modifier", font=get_ctk_font(14, "bold"),
                        text_color=self.colors.accent).pack(anchor="w", pady=(0, 12))
        else:
            tk.Label(right_panel, text="Edit Modifier", font=("Segoe UI", 11, "bold"),
                    bg=self.colors.bg, fg=self.colors.accent).pack(anchor="w", pady=(0, 10))
        
        self.modifier_widgets = {}
        
        # Key, Icon, Label, Tooltip fields
        for field_key, field_label, width in [
            ("key_var", "Key:", 180),
            ("icon_var", "Icon:", 80),
            ("label_var", "Label:", 220),
            ("tooltip_var", "Tooltip:", 340)
        ]:
            row = ctk.CTkFrame(right_panel, fg_color="transparent") if self.use_ctk else tk.Frame(right_panel, bg=self.colors.bg)
            row.pack(fill="x", pady=6)
            
            if self.use_ctk:
                ctk.CTkLabel(row, text=field_label, font=get_ctk_font(13), width=100, anchor="w",
                            **get_ctk_label_colors(self.colors)).pack(side="left")
                self.modifier_widgets[field_key] = tk.StringVar(master=self.root)
                ctk.CTkEntry(row, textvariable=self.modifier_widgets[field_key],
                            font=get_ctk_font(12), width=width, height=34,
                            **get_ctk_entry_colors(self.colors)).pack(side="left", padx=(12, 0))
            else:
                tk.Label(row, text=field_label, font=("Segoe UI", 10), width=10, anchor="w",
                        bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
                self.modifier_widgets[field_key] = tk.StringVar(master=self.root)
                tk.Entry(row, textvariable=self.modifier_widgets[field_key],
                        font=("Segoe UI", 10), width=width//8,
                        bg=self.colors.input_bg, fg=self.colors.fg).pack(side="left", padx=(10, 0))
        
        # Injection (multiline)
        row = ctk.CTkFrame(right_panel, fg_color="transparent") if self.use_ctk else tk.Frame(right_panel, bg=self.colors.bg)
        row.pack(fill="x", pady=8)
        
        if self.use_ctk:
            ctk.CTkLabel(row, text="Injection:", font=get_ctk_font(13),
                        **get_ctk_label_colors(self.colors)).pack(anchor="w")
            self.modifier_widgets["injection"] = ctk.CTkTextbox(
                row, height=100, font=get_ctk_font(12),
                **get_ctk_textbox_colors(self.colors)
            )
        else:
            tk.Label(row, text="Injection:", font=("Segoe UI", 10),
                    bg=self.colors.bg, fg=self.colors.fg).pack(anchor="w")
            self.modifier_widgets["injection"] = tk.Text(
                row, height=4, font=("Consolas", 9),
                bg=self.colors.input_bg, fg=self.colors.fg, wrap="word"
            )
        self.modifier_widgets["injection"].pack(fill="x", pady=(2, 0))
        
        # Forces chat window toggle
        row = ctk.CTkFrame(right_panel, fg_color="transparent") if self.use_ctk else tk.Frame(right_panel, bg=self.colors.bg)
        row.pack(fill="x", pady=8)
        
        self.modifier_widgets["forces_chat_var"] = tk.BooleanVar(master=self.root)
        if self.use_ctk:
            ctk.CTkCheckBox(row, text="Forces chat window",
                           variable=self.modifier_widgets["forces_chat_var"],
                           font=get_ctk_font(13), text_color=self.colors.fg,
                           fg_color=self.colors.accent).pack(anchor="w")
        else:
            tk.Checkbutton(row, text="Forces chat window",
                          variable=self.modifier_widgets["forces_chat_var"],
                          font=("Segoe UI", 10), bg=self.colors.bg, fg=self.colors.fg,
                          selectcolor=self.colors.input_bg).pack(anchor="w")
        
        # Save button
        if self.use_ctk:
            ctk.CTkButton(right_panel, text="💾 Save Modifier", font=get_ctk_font(14),
                         width=160, height=40, **get_ctk_button_colors(self.colors, "success"),
                         command=self._save_current_modifier).pack(anchor="w", pady=(18, 0))
        else:
            tk.Button(right_panel, text="💾 Save Modifier", font=("Segoe UI", 10),
                     bg=self.colors.accent_green, fg="#ffffff",
                     command=self._save_current_modifier).pack(anchor="w", pady=(15, 0))
    
    def _create_groups_tab(self, frame):
        """Create the Groups editing tab."""
        container = ctk.CTkFrame(frame, fg_color="transparent") if self.use_ctk else tk.Frame(frame, bg=self.colors.bg)
        container.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Left panel: group list
        left_panel = ctk.CTkFrame(container, fg_color="transparent", width=260) if self.use_ctk else tk.Frame(container, bg=self.colors.bg, width=260)
        left_panel.pack(side="left", fill="y", padx=(0, 15))
        left_panel.pack_propagate(False)
        
        if self.use_ctk:
            ctk.CTkLabel(left_panel, text="Groups", font=get_ctk_font(14, "bold"),
                        text_color=self.colors.accent).pack(anchor="w", pady=(0, 12))
        else:
            tk.Label(left_panel, text="Groups", font=("Segoe UI", 11, "bold"),
                    bg=self.colors.bg, fg=self.colors.accent).pack(anchor="w", pady=(0, 10))
        
        list_container = ctk.CTkFrame(left_panel, fg_color=self.colors.input_bg, corner_radius=8) if self.use_ctk else tk.Frame(left_panel, bg=self.colors.input_bg)
        list_container.pack(fill="both", expand=True)
        
        self.group_listbox = tk.Listbox(
            list_container, font=("Segoe UI", 12),
            bg=self.colors.input_bg, fg=self.colors.fg,
            selectbackground=self.colors.accent, selectforeground="#ffffff",
            relief="flat", highlightthickness=0, borderwidth=0
        )
        self.group_listbox.pack(fill="both", expand=True, padx=4, pady=4)
        
        # Populate groups
        settings = self.options_data.get("_settings", {})
        groups = settings.get("popup_groups", [])
        for grp in groups:
            self.group_listbox.insert("end", grp.get("name", "Unnamed"))
        
        self.group_listbox.bind('<<ListboxSelect>>', self._on_group_select)
        
        # Buttons
        btn_frame = ctk.CTkFrame(left_panel, fg_color="transparent") if self.use_ctk else tk.Frame(left_panel, bg=self.colors.bg)
        btn_frame.pack(fill="x", pady=(12, 0))
        
        if self.use_ctk:
            ctk.CTkButton(btn_frame, text="➕ Add", font=get_ctk_font(13),
                         width=80, height=34, **get_ctk_button_colors(self.colors, "success"),
                         command=self._add_group).pack(side="left", padx=3)
            ctk.CTkButton(btn_frame, text="🗑️", font=get_ctk_font(13),
                         width=40, height=34, **get_ctk_button_colors(self.colors, "danger"),
                         command=self._delete_group).pack(side="left", padx=3)
        else:
            tk.Button(btn_frame, text="➕ Add", font=("Segoe UI", 9),
                     bg=self.colors.accent_green, fg="#ffffff",
                     command=self._add_group).pack(side="left", padx=2)
            tk.Button(btn_frame, text="🗑️", font=("Segoe UI", 9),
                     bg=self.colors.accent_red, fg="#ffffff",
                     command=self._delete_group).pack(side="left", padx=2)
        
        # Right panel: group editor
        right_panel = ctk.CTkFrame(container, fg_color="transparent") if self.use_ctk else tk.Frame(container, bg=self.colors.bg)
        right_panel.pack(side="left", fill="both", expand=True)
        
        if self.use_ctk:
            ctk.CTkLabel(right_panel, text="Edit Group", font=get_ctk_font(14, "bold"),
                        text_color=self.colors.accent).pack(anchor="w", pady=(0, 12))
        else:
            tk.Label(right_panel, text="Edit Group", font=("Segoe UI", 11, "bold"),
                    bg=self.colors.bg, fg=self.colors.accent).pack(anchor="w", pady=(0, 10))
        
        self.group_widgets = {}
        
        # Name field
        row = ctk.CTkFrame(right_panel, fg_color="transparent") if self.use_ctk else tk.Frame(right_panel, bg=self.colors.bg)
        row.pack(fill="x", pady=8)
        
        if self.use_ctk:
            ctk.CTkLabel(row, text="Name:", font=get_ctk_font(13), width=100, anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(side="left")
            self.group_widgets["name_var"] = tk.StringVar(master=self.root)
            ctk.CTkEntry(row, textvariable=self.group_widgets["name_var"],
                        font=get_ctk_font(13), width=240, height=34,
                        **get_ctk_entry_colors(self.colors)).pack(side="left", padx=(12, 0))
        else:
            tk.Label(row, text="Name:", font=("Segoe UI", 10), width=10, anchor="w",
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            self.group_widgets["name_var"] = tk.StringVar(master=self.root)
            tk.Entry(row, textvariable=self.group_widgets["name_var"],
                    font=("Segoe UI", 10), width=25,
                    bg=self.colors.input_bg, fg=self.colors.fg).pack(side="left", padx=(10, 0))
        
        # Items (one per line)
        row = ctk.CTkFrame(right_panel, fg_color="transparent") if self.use_ctk else tk.Frame(right_panel, bg=self.colors.bg)
        row.pack(fill="both", expand=True, pady=8)
        
        if self.use_ctk:
            ctk.CTkLabel(row, text="Items (one action name per line):", font=get_ctk_font(13),
                        **get_ctk_label_colors(self.colors)).pack(anchor="w")
            self.group_widgets["items"] = ctk.CTkTextbox(
                row, font=get_ctk_font(12),
                **get_ctk_textbox_colors(self.colors)
            )
        else:
            tk.Label(row, text="Items (one action name per line):", font=("Segoe UI", 10),
                    bg=self.colors.bg, fg=self.colors.fg).pack(anchor="w")
            self.group_widgets["items"] = tk.Text(
                row, font=("Segoe UI", 10),
                bg=self.colors.input_bg, fg=self.colors.fg, wrap="word"
            )
        self.group_widgets["items"].pack(fill="both", expand=True, pady=(2, 0))
        
        # Save button
        if self.use_ctk:
            ctk.CTkButton(right_panel, text="💾 Save Group", font=get_ctk_font(14),
                         width=150, height=40, **get_ctk_button_colors(self.colors, "success"),
                         command=self._save_current_group).pack(anchor="w", pady=(18, 0))
        else:
            tk.Button(right_panel, text="💾 Save Group", font=("Segoe UI", 10),
                     bg=self.colors.accent_green, fg="#ffffff",
                     command=self._save_current_group).pack(anchor="w", pady=(15, 0))
    
    def _create_playground_tab(self, frame):
        """Create the Playground tab for testing prompts."""
        container = ctk.CTkFrame(frame, fg_color="transparent") if self.use_ctk else tk.Frame(frame, bg=self.colors.bg)
        container.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Left panel: Configuration
        left_panel = ctk.CTkFrame(container, fg_color="transparent", width=400) if self.use_ctk else tk.Frame(container, bg=self.colors.bg, width=400)
        left_panel.pack(side="left", fill="y", padx=(0, 15))
        left_panel.pack_propagate(False)
        
        if self.use_ctk:
            scroll_left = ctk.CTkScrollableFrame(left_panel, fg_color="transparent")
        else:
            scroll_left = tk.Frame(left_panel, bg=self.colors.bg)
        scroll_left.pack(fill="both", expand=True)
        
        # Mode selector
        if self.use_ctk:
            ctk.CTkLabel(scroll_left, text="🎯 Mode", font=get_ctk_font(14, "bold"),
                        text_color=self.colors.accent).pack(anchor="w", pady=(0, 8))
        else:
            tk.Label(scroll_left, text="🎯 Mode", font=("Segoe UI", 11, "bold"),
                    bg=self.colors.bg, fg=self.colors.accent).pack(anchor="w", pady=(0, 5))
        
        self.playground_mode_var = tk.StringVar(master=self.root, value="action")
        mode_frame = ctk.CTkFrame(scroll_left, fg_color="transparent") if self.use_ctk else tk.Frame(scroll_left, bg=self.colors.bg)
        mode_frame.pack(anchor="w", pady=(0, 15))
        
        if self.use_ctk:
            ctk.CTkRadioButton(mode_frame, text="TextEditTool Action",
                              variable=self.playground_mode_var, value="action",
                              font=get_ctk_font(13), text_color=self.colors.fg,
                              fg_color=self.colors.accent,
                              command=self._on_playground_mode_change).pack(side="left", padx=(0, 20))
            ctk.CTkRadioButton(mode_frame, text="API Endpoint",
                              variable=self.playground_mode_var, value="endpoint",
                              font=get_ctk_font(13), text_color=self.colors.fg,
                              fg_color=self.colors.accent,
                              command=self._on_playground_mode_change).pack(side="left")
        else:
            tk.Radiobutton(mode_frame, text="TextEditTool Action",
                          variable=self.playground_mode_var, value="action",
                          font=("Segoe UI", 10), bg=self.colors.bg, fg=self.colors.fg,
                          command=self._on_playground_mode_change).pack(side="left", padx=(0, 15))
            tk.Radiobutton(mode_frame, text="API Endpoint",
                          variable=self.playground_mode_var, value="endpoint",
                          font=("Segoe UI", 10), bg=self.colors.bg, fg=self.colors.fg,
                          command=self._on_playground_mode_change).pack(side="left")
        
        # Action config frame
        self.action_config_frame = ctk.CTkFrame(scroll_left, fg_color="transparent") if self.use_ctk else tk.Frame(scroll_left, bg=self.colors.bg)
        self.action_config_frame.pack(fill="x", pady=(0, 10))
        
        if self.use_ctk:
            ctk.CTkLabel(self.action_config_frame, text="Select Action:", font=get_ctk_font(13),
                        **get_ctk_label_colors(self.colors)).pack(anchor="w", pady=(0, 8))
        else:
            tk.Label(self.action_config_frame, text="Select Action:", font=("Segoe UI", 10),
                    bg=self.colors.bg, fg=self.colors.fg).pack(anchor="w", pady=(0, 5))
        
        self.playground_action_var = tk.StringVar(master=self.root)
        action_names = [name for name in sorted(self.options_data.keys()) if name != "_settings"]
        
        if self.use_ctk:
            self.playground_action_combo = ctk.CTkComboBox(
                self.action_config_frame, variable=self.playground_action_var,
                values=action_names, width=340, height=34, state="readonly", font=get_ctk_font(13),
                **get_ctk_combobox_colors(self.colors),
                command=lambda x: self._on_playground_action_change()
            )
        else:
            from tkinter import ttk
            self.playground_action_combo = ttk.Combobox(
                self.action_config_frame, textvariable=self.playground_action_var,
                values=action_names, state="readonly", width=35
            )
            self.playground_action_combo.bind('<<ComboboxSelected>>', self._on_playground_action_change)
        self.playground_action_combo.pack(anchor="w", pady=(0, 10))
        
        # Modifiers section
        if self.use_ctk:
            ctk.CTkLabel(self.action_config_frame, text="🎛️ Modifiers:", font=get_ctk_font(13),
                        **get_ctk_label_colors(self.colors)).pack(anchor="w", pady=(8, 8))
            
            self.playground_mod_scroll = ctk.CTkScrollableFrame(
                self.action_config_frame, height=120, fg_color="transparent"
            )
        else:
            tk.Label(self.action_config_frame, text="🎛️ Modifiers:", font=("Segoe UI", 10),
                    bg=self.colors.bg, fg=self.colors.fg).pack(anchor="w", pady=(5, 5))
            self.playground_mod_scroll = tk.Frame(self.action_config_frame, bg=self.colors.bg)
            
        self.playground_mod_scroll.pack(fill="x", pady=(0, 10))
        
        # Populate modifiers
        self.playground_modifier_vars = {}
        modifiers = self.options_data.get("_settings", {}).get("modifiers", [])
        
        for mod in modifiers:
            key = mod.get("key")
            var = tk.BooleanVar(value=False)
            self.playground_modifier_vars[key] = var
            label = f"{mod.get('icon', '')} {mod.get('label', key)}"
            
            if self.use_ctk:
                ctk.CTkCheckBox(
                    self.playground_mod_scroll, text=label, variable=var,
                    font=get_ctk_font(12), text_color=self.colors.fg,
                    fg_color=self.colors.accent, hover_color=self.colors.lavender,
                    command=self._update_playground_preview
                ).pack(anchor="w", pady=3)
            else:
                tk.Checkbutton(
                    self.playground_mod_scroll, text=label, variable=var,
                    font=("Segoe UI", 9), bg=self.colors.bg, fg=self.colors.fg,
                    selectcolor=self.colors.input_bg,
                    command=self._update_playground_preview
                ).pack(anchor="w", pady=2)

        # Custom Input (for _Custom / _Ask)
        self.custom_input_frame = ctk.CTkFrame(self.action_config_frame, fg_color="transparent") if self.use_ctk else tk.Frame(self.action_config_frame, bg=self.colors.bg)
        # Not packed initially - shown only when needed
        
        if self.use_ctk:
            ctk.CTkLabel(self.custom_input_frame, text="✏️ Custom Input:", font=get_ctk_font(13),
                        **get_ctk_label_colors(self.colors)).pack(anchor="w", pady=(0, 8))
            self.playground_custom_var = tk.StringVar()
            self.playground_custom_entry = ctk.CTkEntry(
                self.custom_input_frame, textvariable=self.playground_custom_var,
                font=get_ctk_font(13), height=34, **get_ctk_entry_colors(self.colors)
            )
            self.playground_custom_entry.pack(fill="x")
            self.playground_custom_entry.bind('<KeyRelease>', lambda e: self._update_playground_preview())
        else:
            tk.Label(self.custom_input_frame, text="✏️ Custom Input:", font=("Segoe UI", 10),
                    bg=self.colors.bg, fg=self.colors.fg).pack(anchor="w", pady=(0, 5))
            self.playground_custom_var = tk.StringVar()
            self.playground_custom_entry = tk.Entry(
                self.custom_input_frame, textvariable=self.playground_custom_var,
                font=("Segoe UI", 10), bg=self.colors.input_bg, fg=self.colors.fg
            )
            self.playground_custom_entry.pack(fill="x")
            self.playground_custom_entry.bind('<KeyRelease>', lambda e: self._update_playground_preview())

        if action_names:
            if self.use_ctk:
                self.playground_action_combo.set(action_names[0])
            else:
                self.playground_action_combo.current(0)
                
        # Endpoint Config Frame (initially hidden)
        self.endpoint_config_frame = ctk.CTkFrame(scroll_left, fg_color="transparent") if self.use_ctk else tk.Frame(scroll_left, bg=self.colors.bg)
        
        # Endpoint selector
        if self.use_ctk:
            ctk.CTkLabel(self.endpoint_config_frame, text="Select Endpoint:", font=get_ctk_font(13),
                        **get_ctk_label_colors(self.colors)).pack(anchor="w", pady=(0, 8))
        else:
            tk.Label(self.endpoint_config_frame, text="Select Endpoint:", font=("Segoe UI", 10),
                    bg=self.colors.bg, fg=self.colors.fg).pack(anchor="w", pady=(0, 5))
            
        self.playground_endpoint_var = tk.StringVar()
        if self.use_ctk:
            self.playground_endpoint_combo = ctk.CTkComboBox(
                self.endpoint_config_frame, variable=self.playground_endpoint_var,
                values=[], width=340, height=34, state="readonly", font=get_ctk_font(13),
                **get_ctk_combobox_colors(self.colors),
                command=lambda x: self._update_endpoint_preview()
            )
        else:
            self.playground_endpoint_combo = ttk.Combobox(
                self.endpoint_config_frame, textvariable=self.playground_endpoint_var,
                values=[], state="readonly", width=35
            )
            self.playground_endpoint_combo.bind('<<ComboboxSelected>>', lambda e: self._update_endpoint_preview())
        self.playground_endpoint_combo.pack(anchor="w", pady=(0, 10))
        
        # Language input
        if self.use_ctk:
            ctk.CTkLabel(self.endpoint_config_frame, text="Language (for {lang}):", font=get_ctk_font(13),
                        **get_ctk_label_colors(self.colors)).pack(anchor="w", pady=(0, 8))
            self.playground_lang_var = tk.StringVar(value="English")
            lang_entry = ctk.CTkEntry(
                self.endpoint_config_frame, textvariable=self.playground_lang_var,
                font=get_ctk_font(13), height=34, **get_ctk_entry_colors(self.colors)
            )
            lang_entry.pack(fill="x", pady=(0, 10))
            lang_entry.bind('<KeyRelease>', lambda e: self._update_endpoint_preview())
        else:
            tk.Label(self.endpoint_config_frame, text="Language (for {lang}):", font=("Segoe UI", 10),
                    bg=self.colors.bg, fg=self.colors.fg).pack(anchor="w", pady=(0, 5))
            self.playground_lang_var = tk.StringVar(value="English")
            lang_entry = tk.Entry(
                self.endpoint_config_frame, textvariable=self.playground_lang_var,
                font=("Segoe UI", 10), bg=self.colors.input_bg, fg=self.colors.fg
            )
            lang_entry.pack(fill="x", pady=(0, 10))
            lang_entry.bind('<KeyRelease>', lambda e: self._update_endpoint_preview())
        
        # Image container
        if self.use_ctk:
            self.image_container_frame = ctk.CTkFrame(
                self.endpoint_config_frame, fg_color=self.colors.surface0,
                corner_radius=6, border_width=1, border_color=self.colors.border
            )
        else:
            self.image_container_frame = tk.Frame(
                self.endpoint_config_frame, bg=self.colors.surface0,
                highlightbackground=self.colors.border, highlightthickness=1
            )
        self.image_container_frame.pack(fill="x", pady=(0, 10))
        
        if self.use_ctk:
            self.image_drop_zone = ctk.CTkLabel(
                self.image_container_frame, text="📷 No image selected",
                font=get_ctk_font(13), text_color=self.colors.blockquote
            )
        else:
            self.image_drop_zone = tk.Label(
                self.image_container_frame, text="📷 No image selected",
                font=("Segoe UI", 10), bg=self.colors.surface0, fg=self.colors.blockquote
            )
        self.image_drop_zone.pack(fill="both", expand=True, padx=10, pady=20)
        
        # Image buttons
        btn_row = ctk.CTkFrame(self.endpoint_config_frame, fg_color="transparent") if self.use_ctk else tk.Frame(self.endpoint_config_frame, bg=self.colors.bg)
        btn_row.pack(fill="x", pady=(0, 10))
        
        if self.use_ctk:
            ctk.CTkButton(btn_row, text="📁 Select", font=get_ctk_font(13), width=100, height=34,
                         **get_ctk_button_colors(self.colors, "secondary"),
                         command=self._select_playground_image).pack(side="left", padx=4)
            ctk.CTkButton(btn_row, text="📋 Paste", font=get_ctk_font(13), width=100, height=34,
                         **get_ctk_button_colors(self.colors, "secondary"),
                         command=self._paste_playground_image).pack(side="left", padx=4)
            ctk.CTkButton(btn_row, text="🗑️ Clear", font=get_ctk_font(13), width=100, height=34,
                         **get_ctk_button_colors(self.colors, "danger"),
                         command=self._clear_playground_image).pack(side="left", padx=4)
        else:
            tk.Button(btn_row, text="📁 Select", font=("Segoe UI", 9), command=self._select_playground_image).pack(side="left", padx=2)
            tk.Button(btn_row, text="📋 Paste", font=("Segoe UI", 9), command=self._paste_playground_image).pack(side="left", padx=2)
            tk.Button(btn_row, text="🗑️ Clear", font=("Segoe UI", 9), command=self._clear_playground_image).pack(side="left", padx=2)
        
        # Sample text container (for hiding/showing)
        self.sample_text_container = ctk.CTkFrame(scroll_left, fg_color="transparent") if self.use_ctk else tk.Frame(scroll_left, bg=self.colors.bg)
        self.sample_text_container.pack(fill="x")
        
        if self.use_ctk:
            ctk.CTkLabel(self.sample_text_container, text="📄 Sample Text:", font=get_ctk_font(13),
                        **get_ctk_label_colors(self.colors)).pack(anchor="w", pady=(12, 8))
            self.playground_sample_text = ctk.CTkTextbox(
                self.sample_text_container, height=120, font=get_ctk_font(12),
                **get_ctk_textbox_colors(self.colors)
            )
        else:
            tk.Label(self.sample_text_container, text="📄 Sample Text:", font=("Segoe UI", 10),
                    bg=self.colors.bg, fg=self.colors.fg).pack(anchor="w", pady=(10, 5))
            self.playground_sample_text = tk.Text(
                self.sample_text_container, height=5, font=("Segoe UI", 10),
                bg=self.colors.input_bg, fg=self.colors.fg, wrap="word"
            )
        self.playground_sample_text.pack(fill="x", pady=(0, 10))
        
        # Bind sample text changes
        if self.use_ctk:
            self.playground_sample_text.insert("0.0", "The quick brown fox jumps over the lazy dog.")
            self.playground_sample_text.bind('<KeyRelease>', lambda e: self._update_playground_preview())
        else:
            self.playground_sample_text.insert("1.0", "The quick brown fox jumps over the lazy dog.")
            self.playground_sample_text.bind('<KeyRelease>', lambda e: self._update_playground_preview())

        # API Settings section (below sample text)
        if self.use_ctk:
            ctk.CTkLabel(scroll_left, text="⚙️ API Settings:", font=get_ctk_font(14, "bold"),
                        **get_ctk_label_colors(self.colors)).pack(anchor="w", pady=(18, 8))
        else:
            tk.Label(scroll_left, text="⚙️ API Settings:", font=("Segoe UI", 10, "bold"),
                    bg=self.colors.bg, fg=self.colors.fg).pack(anchor="w", pady=(15, 5))
            
        api_frame = ctk.CTkFrame(scroll_left, fg_color="transparent") if self.use_ctk else tk.Frame(scroll_left, bg=self.colors.bg)
        api_frame.pack(fill="x", pady=(0, 10))
        
        # Provider & Model
        if self.use_ctk:
            ctk.CTkLabel(api_frame, text="Provider:", font=get_ctk_font(12), width=80, anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(side="left")
            self.playground_provider_var = tk.StringVar(value="google")
            ctk.CTkComboBox(
                api_frame, variable=self.playground_provider_var,
                values=["google", "openrouter", "custom"],
                width=130, height=32, state="readonly", font=get_ctk_font(12),
                **get_ctk_combobox_colors(self.colors)
            ).pack(side="left", padx=(8, 15))
            
            ctk.CTkLabel(api_frame, text="Model:", font=get_ctk_font(12), width=60, anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(side="left")
            self.playground_model_var = tk.StringVar()
            ctk.CTkEntry(
                api_frame, textvariable=self.playground_model_var,
                font=get_ctk_font(12), height=32, **get_ctk_entry_colors(self.colors)
            ).pack(side="left", padx=(8, 0), fill="x", expand=True)
        else:
            tk.Label(api_frame, text="Provider:", font=("Segoe UI", 9),
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            self.playground_provider_var = tk.StringVar(value="google")
            ttk.Combobox(
                api_frame, textvariable=self.playground_provider_var,
                values=["google", "openrouter", "custom"],
                state="readonly", width=12
            ).pack(side="left", padx=(5, 10))
            
            tk.Label(api_frame, text="Model:", font=("Segoe UI", 9),
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            self.playground_model_var = tk.StringVar()
            tk.Entry(
                api_frame, textvariable=self.playground_model_var,
                font=("Segoe UI", 9), bg=self.colors.input_bg, fg=self.colors.fg, width=15
            ).pack(side="left", padx=(5, 0), fill="x", expand=True)

        # Load defaults
        try:
            from ..config import load_config
            config, _, _, _ = load_config()
            default_provider = config.get("default_provider", "google")
            self.playground_provider_var.set(default_provider)
            self.playground_model_var.set(config.get(f"{default_provider}_model", ""))
        except:
            pass

        # Test button
        btn_frame = ctk.CTkFrame(scroll_left, fg_color="transparent") if self.use_ctk else tk.Frame(scroll_left, bg=self.colors.bg)
        btn_frame.pack(fill="x", pady=(10, 0))
        
        if self.use_ctk:
            ctk.CTkButton(btn_frame, text="🧪 Test with API", font=get_ctk_font(14),
                         width=160, height=42, **get_ctk_button_colors(self.colors, "primary"),
                         command=self._test_playground_with_api).pack(side="left", padx=(0, 15))
            self.playground_test_status = ctk.CTkLabel(btn_frame, text="", font=get_ctk_font(12),
                                                       text_color=self.colors.fg)
        else:
            tk.Button(btn_frame, text="🧪 Test with API", font=("Segoe UI", 10),
                     bg=self.colors.accent, fg="#ffffff",
                     command=self._test_playground_with_api).pack(side="left", padx=(0, 10))
            self.playground_test_status = tk.Label(btn_frame, text="", font=("Segoe UI", 9),
                                                   bg=self.colors.bg, fg=self.colors.fg)
        self.playground_test_status.pack(side="left")
        
        # Right panel: Preview
        right_panel = ctk.CTkFrame(container, fg_color="transparent") if self.use_ctk else tk.Frame(container, bg=self.colors.bg)
        right_panel.pack(side="left", fill="both", expand=True)
        
        # System prompt preview
        sys_header = ctk.CTkFrame(right_panel, fg_color="transparent") if self.use_ctk else tk.Frame(right_panel, bg=self.colors.bg)
        sys_header.pack(fill="x", pady=(0, 5))
        
        if self.use_ctk:
            ctk.CTkLabel(sys_header, text="📝 System Prompt Preview", font=get_ctk_font(14, "bold"),
                        text_color=self.colors.accent).pack(side="left")
            ctk.CTkButton(sys_header, text="📋 Copy", font=get_ctk_font(12), width=80, height=30,
                         **get_ctk_button_colors(self.colors, "secondary"),
                         command=lambda: self._copy_preview("system")).pack(side="right")
            self.playground_system_preview = ctk.CTkTextbox(
                right_panel, height=180, font=get_ctk_font(12),
                state="disabled", **get_ctk_textbox_colors(self.colors)
            )
        else:
            tk.Label(sys_header, text="📝 System Prompt Preview", font=("Segoe UI", 11, "bold"),
                    bg=self.colors.bg, fg=self.colors.accent).pack(side="left")
            tk.Button(sys_header, text="📋 Copy", font=("Segoe UI", 8),
                     command=lambda: self._copy_preview("system")).pack(side="right")
            self.playground_system_preview = tk.Text(
                right_panel, height=8, font=("Consolas", 10),
                bg=self.colors.surface0, fg=self.colors.fg, wrap="word", state="disabled"
            )
        self.playground_system_preview.pack(fill="x", pady=(0, 10))
        
        # User message preview
        user_header = ctk.CTkFrame(right_panel, fg_color="transparent") if self.use_ctk else tk.Frame(right_panel, bg=self.colors.bg)
        user_header.pack(fill="x", pady=(0, 5))
        
        if self.use_ctk:
            ctk.CTkLabel(user_header, text="💬 User Message Preview", font=get_ctk_font(14, "bold"),
                        text_color=self.colors.accent).pack(side="left")
            ctk.CTkButton(user_header, text="📋 Copy", font=get_ctk_font(12), width=80, height=30,
                         **get_ctk_button_colors(self.colors, "secondary"),
                         command=lambda: self._copy_preview("user")).pack(side="right")
            self.playground_user_preview = ctk.CTkTextbox(
                right_panel, font=get_ctk_font(12),
                state="disabled", **get_ctk_textbox_colors(self.colors)
            )
        else:
            tk.Label(user_header, text="💬 User Message Preview", font=("Segoe UI", 11, "bold"),
                    bg=self.colors.bg, fg=self.colors.accent).pack(side="left")
            tk.Button(user_header, text="📋 Copy", font=("Segoe UI", 8),
                     command=lambda: self._copy_preview("user")).pack(side="right")
            self.playground_user_preview = tk.Text(
                right_panel, font=("Consolas", 10),
                bg=self.colors.surface0, fg=self.colors.fg, wrap="word", state="disabled"
            )
        self.playground_user_preview.pack(fill="both", expand=True)

        # Metadata Footer
        meta_frame = ctk.CTkFrame(right_panel, fg_color="transparent") if self.use_ctk else tk.Frame(right_panel, bg=self.colors.bg)
        meta_frame.pack(fill="x", pady=(10, 0))
        
        if self.use_ctk:
            self.playground_meta_label = ctk.CTkLabel(
                meta_frame,
                text="📊 Tokens: ~0 | Type: edit | Mode: Replace",
                font=get_ctk_font(12),
                text_color=self.colors.blockquote
            )
        else:
            self.playground_meta_label = tk.Label(
                meta_frame,
                text="📊 Tokens: ~0 | Type: edit | Mode: Replace",
                font=("Segoe UI", 9),
                bg=self.colors.bg, fg=self.colors.blockquote
            )
        self.playground_meta_label.pack(anchor="w")
        
        # Initial preview update
        self.root.after(100, self._update_playground_preview)
    
    def _on_playground_mode_change(self):
        """Handle mode switch between action and endpoint."""
        mode = self.playground_mode_var.get()
        
        if mode == "action":
            self.action_config_frame.pack(fill="x", pady=(0, 10))
            self.endpoint_config_frame.pack_forget()
            self.sample_text_container.pack(fill="x")
            self._update_playground_preview()
        else:
            self.action_config_frame.pack_forget()
            self.endpoint_config_frame.pack(fill="x", pady=(0, 10))
            self.sample_text_container.pack_forget()
            self._populate_endpoint_list()
            self._update_endpoint_preview()
    
    def _on_playground_action_change(self, event=None):
        """Handle action selection change."""
        action_name = self.playground_action_var.get()
        if action_name in ("_Custom", "_Ask"):
            self.custom_input_frame.pack(fill="x", pady=(5, 0))
        else:
            self.custom_input_frame.pack_forget()
        self._update_playground_preview()
    
    def _populate_endpoint_list(self):
        """Populate the endpoint list from web_server config."""
        try:
            from ..web_server import ENDPOINTS
            endpoints = sorted(list(ENDPOINTS.keys()))
            if self.use_ctk:
                self.playground_endpoint_combo.configure(values=endpoints)
            else:
                self.playground_endpoint_combo['values'] = endpoints
            
            if endpoints:
                if self.use_ctk:
                    self.playground_endpoint_combo.set(endpoints[0])
                else:
                    self.playground_endpoint_combo.current(0)
                self.playground_endpoint_var.set(endpoints[0])
        except (ImportError, AttributeError):
            pass
    
    def _update_playground_preview(self, event=None):
        """Update the live preview based on current action configuration."""
        if self.playground_mode_var.get() == "endpoint":
            return
        
        action_name = self.playground_action_var.get()
        if not action_name:
            return
        
        action_data = self.options_data.get(action_name, {})
        settings = self.options_data.get("_settings", {})
        
        # Build system prompt parts
        system_parts = []
        prompt_type = action_data.get("prompt_type", "edit")
        show_chat = action_data.get("show_chat_window_instead_of_replace", False)
        
        if show_chat:
            global_instr = settings.get("chat_window_system_instruction", "")
        else:
            global_instr = settings.get("chat_system_instruction", "")
        if global_instr:
            system_parts.append(global_instr)
        
        sys_prompt = action_data.get("system_prompt", action_data.get("instruction", ""))
        if sys_prompt:
            system_parts.append(sys_prompt)
        
        # Add modifier injections
        for key, var in self.playground_modifier_vars.items():
            if var.get():
                for mod in settings.get("modifiers", []):
                    if mod.get("key") == key:
                        injection = mod.get("injection", "")
                        if injection:
                            system_parts.append(injection)
        
        full_system = "\n\n".join(system_parts)
        
        # Build user message
        user_parts = []
        if prompt_type == "general":
            output_rules = settings.get("base_output_rules_general", "")
        else:
            output_rules = settings.get("base_output_rules", "")
        if output_rules:
            user_parts.append(output_rules)
        
        task = action_data.get("task", action_data.get("prefix", ""))
        custom_input = self.playground_custom_var.get()
        
        if task:
            if "{input}" in task and custom_input:
                task = task.replace("{input}", custom_input)
            elif action_name in ("_Custom", "_Ask") and custom_input:
                task = custom_input
            user_parts.append(f"Task: {task}")
        elif action_name in ("_Custom", "_Ask") and custom_input:
            user_parts.append(f"Task: {custom_input}")
        
        text_delimiter = settings.get("text_delimiter", "\n\n<text_to_process>\n")
        text_delimiter_close = settings.get("text_delimiter_close", "\n</text_to_process>")
        
        if self.use_ctk:
            sample_text = self.playground_sample_text.get("0.0", "end").strip()
        else:
            sample_text = self.playground_sample_text.get("1.0", "end").strip()
        
        user_message = "\n\n".join(user_parts)
        if sample_text:
            user_message += text_delimiter + sample_text + text_delimiter_close
        
        self._set_preview_text(self.playground_system_preview, full_system, "system")
        self._set_preview_text(self.playground_user_preview, user_message, "user")
        
        # Update metadata
        total_chars = len(full_system) + len(user_message)
        token_estimate = total_chars // 4
        response_mode = "Chat Window" if show_chat else "Replace"
        
        if self.use_ctk:
            self.playground_meta_label.configure(
                text=f"📊 Tokens: ~{token_estimate} | Type: {prompt_type} | Mode: {response_mode}"
            )
        else:
            self.playground_meta_label.configure(
                text=f"📊 Tokens: ~{token_estimate} | Type: {prompt_type} | Mode: {response_mode}"
            )
    
    def _update_endpoint_preview(self):
        """Update endpoint mode preview."""
        endpoint_name = self.playground_endpoint_var.get()
        if not endpoint_name:
            return
        
        try:
            from ..web_server import ENDPOINTS
            prompt_template = ENDPOINTS.get(endpoint_name, "")
        except:
            prompt_template = "(Could not load endpoint)"
        
        lang = self.playground_lang_var.get() or "English"
        prompt = prompt_template.replace("{lang}", lang)
        
        self._set_preview_text(self.playground_system_preview,
                              "(Endpoints use direct prompts without system message)", "system")
        self._set_preview_text(self.playground_user_preview, prompt, "user")
        
        token_estimate = len(prompt) // 4
        image_info = f" | 🖼️ {self.playground_image_name}" if self.playground_image_base64 else " | ⚠️ No image"
        
        if self.use_ctk:
            self.playground_meta_label.configure(
                text=f"📊 Tokens: ~{token_estimate} | Endpoint: {endpoint_name}{image_info}"
            )
        else:
            self.playground_meta_label.configure(
                text=f"📊 Tokens: ~{token_estimate} | Endpoint: {endpoint_name}{image_info}"
            )
    
    def _set_preview_text(self, widget, text, preview_type):
        """Helper to set preview text."""
        if self.use_ctk:
            widget.configure(state="normal")
            widget.delete("0.0", "end")
            widget.insert("0.0", text)
            widget.configure(state="disabled")
        else:
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", text)
            widget.configure(state="disabled")
    
    def _copy_preview(self, preview_type):
        """Copy preview content to clipboard."""
        widget = self.playground_system_preview if preview_type == "system" else self.playground_user_preview
        if self.use_ctk:
            content = widget.get("0.0", "end").strip()
        else:
            content = widget.get("1.0", "end").strip()
        try:
            pyperclip.copy(content)
            if self.use_ctk:
                self.playground_test_status.configure(text="✅ Copied!", text_color=self.colors.accent_green)
            else:
                self.playground_test_status.configure(text="✅ Copied!", fg=self.colors.accent_green)
            self.root.after(2000, lambda: self._clear_test_status())
        except Exception as e:
            if self.use_ctk:
                self.playground_test_status.configure(text=f"❌ Copy failed: {e}", text_color=self.colors.accent_red)
            else:
                self.playground_test_status.configure(text=f"❌ Copy failed: {e}", fg=self.colors.accent_red)
    
    # --- Image Handling ---
    
    def _select_playground_image(self):
        """Select an image file for endpoint testing."""
        path = filedialog.askopenfilename(
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp")]
        )
        if path:
            self._load_playground_image(path)
    
    def _paste_playground_image(self):
        """Paste image from clipboard."""
        try:
            from PIL import ImageGrab, Image
            
            img = ImageGrab.grabclipboard()
            if img:
                if img.mode == 'RGBA':
                    bg = Image.new('RGB', img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg
                
                from io import BytesIO
                buffered = BytesIO()
                img.save(buffered, format="JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
                
                self.playground_image_base64 = img_str
                self.playground_image_mime = "image/jpeg"
                self.playground_image_name = "Pasted Image"
                
                self._show_image_preview(img)
                self._update_endpoint_preview()
            else:
                messagebox.showinfo("Paste", "No image in clipboard", parent=self.root)
        except Exception as e:
            messagebox.showerror("Paste Error", str(e), parent=self.root)
    
    def _load_playground_image(self, filepath):
        """Load image from file."""
        try:
            from PIL import Image
            from io import BytesIO
            
            img = Image.open(filepath)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            buffered = BytesIO()
            img.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            self.playground_image_base64 = img_str
            self.playground_image_mime = "image/jpeg"
            self.playground_image_name = os.path.basename(filepath)
            
            self._show_image_preview(img)
            self._update_endpoint_preview()
        except ImportError:
            with open(filepath, "rb") as f:
                img_bytes = f.read()
                self.playground_image_base64 = base64.b64encode(img_bytes).decode("utf-8")
                self.playground_image_mime = "image/jpeg"
                self.playground_image_name = os.path.basename(filepath)
                self._show_image_preview_text_only(os.path.basename(filepath), f"{len(img_bytes)//1024} KB")
                self._update_endpoint_preview()
        except Exception as e:
            messagebox.showerror("Image Error", f"Failed to load image: {e}", parent=self.root)
    
    def _show_image_preview(self, pil_image):
        """Show thumbnail preview of image."""
        try:
            if self.use_ctk:
                ctk_img = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(100, 100))
                self.image_drop_zone.configure(image=ctk_img, text="")
                self.image_drop_zone._image = ctk_img  # Keep reference
            else:
                from PIL import ImageTk
                pil_image.thumbnail((100, 100))
                tk_img = ImageTk.PhotoImage(pil_image)
                self.image_drop_zone.configure(image=tk_img, text="")
                self.image_drop_zone.image = tk_img
        except Exception:
            self.image_drop_zone.configure(text=f"📷 {self.playground_image_name}")
    
    def _show_image_preview_text_only(self, filename, size):
        """Fallback preview."""
        self.image_drop_zone.configure(text=f"📷 {filename}\n({size})")
    
    def _clear_playground_image(self):
        """Clear the selected image."""
        self.playground_image_base64 = None
        self.playground_image_mime = None
        self.playground_image_name = None
        if self.use_ctk:
            self.image_drop_zone.configure(image=None, text="📷 No image selected")
        else:
            self.image_drop_zone.configure(image='', text="📷 No image selected")
            if hasattr(self.image_drop_zone, 'image'):
                self.image_drop_zone.image = None
        self._update_endpoint_preview()
    
    # --- API Testing ---
    
    def _test_playground_with_api(self):
        """Send the current prompt to the API for testing."""
        if self.use_ctk:
            self.playground_test_status.configure(text="⏳ Sending request...", text_color=self.colors.fg)
        else:
            self.playground_test_status.configure(text="⏳ Sending request...", fg=self.colors.fg)
        self.root.update()
        
        try:
            if self.playground_mode_var.get() == "endpoint":
                result, error = self._test_endpoint_prompt()
            else:
                result, error = self._test_action_prompt()
            self._show_test_result(result, error)
        except Exception as e:
            if self.use_ctk:
                self.playground_test_status.configure(text=f"❌ Error: {e}", text_color=self.colors.accent_red)
            else:
                self.playground_test_status.configure(text=f"❌ Error: {e}", fg=self.colors.accent_red)
    
    def _test_endpoint_prompt(self):
        """Test an endpoint prompt with image support."""
        if not self.playground_image_base64:
            return None, "No image selected. Endpoints require an image for testing."
        
        from ..api_client import call_api_with_retry
        from ..config import load_config
        
        config, ai_params_loaded, endpoints, loaded_keys = load_config()
        
        from ..key_manager import KeyManager
        key_managers = {}
        for provider in ["custom", "openrouter", "google"]:
            key_managers[provider] = KeyManager(loaded_keys.get(provider, []), provider)
        
        if self.use_ctk:
            prompt = self.playground_user_preview.get("0.0", "end").strip()
        else:
            prompt = self.playground_user_preview.get("1.0", "end").strip()
        
        data_url = f"data:{self.playground_image_mime};base64,{self.playground_image_base64}"
        messages = [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": prompt}
            ]
        }]
        
        ai_params = {k: v for k, v in ai_params_loaded.items() if v is not None}
        provider = self.playground_provider_var.get()
        model = self.playground_model_var.get()
        ai_params["max_tokens"] = 1024
        
        return call_api_with_retry(provider, messages, model, config, ai_params, key_managers)
    
    def _test_action_prompt(self):
        """Test an action prompt with the API."""
        from ..api_client import call_api_with_retry
        from ..config import load_config
        
        config, ai_params_loaded, endpoints, loaded_keys = load_config()
        
        from ..key_manager import KeyManager
        key_managers = {}
        for provider in ["custom", "openrouter", "google"]:
            key_managers[provider] = KeyManager(loaded_keys.get(provider, []), provider)
        
        if self.use_ctk:
            system_prompt = self.playground_system_preview.get("0.0", "end").strip()
            user_message = self.playground_user_preview.get("0.0", "end").strip()
        else:
            system_prompt = self.playground_system_preview.get("1.0", "end").strip()
            user_message = self.playground_user_preview.get("1.0", "end").strip()
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        ai_params = {k: v for k, v in ai_params_loaded.items() if v is not None}
        provider = self.playground_provider_var.get()
        model = self.playground_model_var.get()
        
        return call_api_with_retry(provider, messages, model, config, ai_params, key_managers)
    
    def _show_test_result(self, result: Optional[str], error: Optional[str]):
        """Show API test result in a popup."""
        if error:
            if self.use_ctk:
                self.playground_test_status.configure(text=f"❌ {error[:40]}...", text_color=self.colors.accent_red)
            else:
                self.playground_test_status.configure(text=f"❌ {error[:40]}...", fg=self.colors.accent_red)
            messagebox.showerror("API Test Error", error, parent=self.root)
        else:
            if self.use_ctk:
                self.playground_test_status.configure(text="✅ Success!", text_color=self.colors.accent_green)
            else:
                self.playground_test_status.configure(text="✅ Success!", fg=self.colors.accent_green)
            
            # Show result in a simple dialog
            result_window = ctk.CTkToplevel(self.root) if self.use_ctk else tk.Toplevel(self.root)
            result_window.title("API Test Result")
            result_window.geometry("600x400")
            result_window.transient(self.root)
            
            if self.use_ctk:
                result_window.configure(fg_color=self.colors.bg)
                ctk.CTkLabel(result_window, text="📤 API Response:", font=get_ctk_font(12, "bold"),
                            text_color=self.colors.accent).pack(anchor="w", padx=15, pady=(15, 10))
                result_text = ctk.CTkTextbox(result_window, font=get_ctk_font(10),
                                            **get_ctk_textbox_colors(self.colors))
                result_text.pack(fill="both", expand=True, padx=15, pady=(0, 10))
                result_text.insert("0.0", result or "(empty response)")
                result_text.configure(state="disabled")
                
                ctk.CTkButton(result_window, text="Close", font=get_ctk_font(11),
                             width=100, **get_ctk_button_colors(self.colors, "primary"),
                             command=result_window.destroy).pack(pady=(0, 15))
            else:
                result_window.configure(bg=self.colors.bg)
                tk.Label(result_window, text="📤 API Response:", font=("Segoe UI", 11, "bold"),
                        bg=self.colors.bg, fg=self.colors.accent).pack(anchor="w", padx=15, pady=(15, 10))
                result_text = tk.Text(result_window, font=("Consolas", 10),
                                     bg=self.colors.surface0, fg=self.colors.fg, wrap="word")
                result_text.pack(fill="both", expand=True, padx=15, pady=(0, 10))
                result_text.insert("1.0", result or "(empty response)")
                result_text.configure(state="disabled")
                
                tk.Button(result_window, text="Close", font=("Segoe UI", 10),
                         bg=self.colors.accent, fg="#ffffff",
                         command=result_window.destroy).pack(pady=(0, 15))
        
        self.root.after(3000, lambda: self._clear_test_status())
    
    def _clear_test_status(self):
        """Clear the test status label."""
        if self.use_ctk:
            self.playground_test_status.configure(text="")
        else:
            self.playground_test_status.configure(text="")
    
    # Event handlers
    
    def _on_action_select(self, event):
        """Handle action selection."""
        selection = self.action_listbox.curselection()
        if not selection:
            return
        
        display_text = self.action_listbox.get(selection[0])
        parts = display_text.split(" ", 1)
        action_name = parts[1] if len(parts) > 1 else parts[0]
        
        self.current_action = action_name
        action_data = self.options_data.get(action_name, {})
        
        # Populate editor
        if self.use_ctk:
            self.editor_widgets["name"].configure(text=action_name)
        else:
            self.editor_widgets["name"].configure(text=action_name)
        
        self.editor_widgets["icon_var"].set(action_data.get("icon", ""))
        self.editor_widgets["prompt_type_var"].set(action_data.get("prompt_type", "edit"))
        
        if self.use_ctk:
            self.editor_widgets["system_prompt"].delete("0.0", "end")
            self.editor_widgets["system_prompt"].insert("0.0", action_data.get("system_prompt", ""))
        else:
            self.editor_widgets["system_prompt"].delete("1.0", "end")
            self.editor_widgets["system_prompt"].insert("1.0", action_data.get("system_prompt", ""))
        
        self.editor_widgets["task_var"].set(action_data.get("task", ""))
        self.editor_widgets["show_chat_var"].set(
            action_data.get("show_chat_window_instead_of_replace", False))
    
    def _on_modifier_select(self, event):
        """Handle modifier selection."""
        selection = self.modifier_listbox.curselection()
        if not selection:
            return
        
        settings = self.options_data.get("_settings", {})
        modifiers = settings.get("modifiers", [])
        
        if selection[0] < len(modifiers):
            mod = modifiers[selection[0]]
            self.modifier_widgets["key_var"].set(mod.get("key", ""))
            self.modifier_widgets["icon_var"].set(mod.get("icon", ""))
            self.modifier_widgets["label_var"].set(mod.get("label", ""))
            self.modifier_widgets["tooltip_var"].set(mod.get("tooltip", ""))
            
            if self.use_ctk:
                self.modifier_widgets["injection"].delete("0.0", "end")
                self.modifier_widgets["injection"].insert("0.0", mod.get("injection", ""))
            else:
                self.modifier_widgets["injection"].delete("1.0", "end")
                self.modifier_widgets["injection"].insert("1.0", mod.get("injection", ""))
            
            self.modifier_widgets["forces_chat_var"].set(mod.get("forces_chat_window", False))
    
    def _on_group_select(self, event):
        """Handle group selection."""
        selection = self.group_listbox.curselection()
        if not selection:
            return
        
        settings = self.options_data.get("_settings", {})
        groups = settings.get("popup_groups", [])
        
        if selection[0] < len(groups):
            grp = groups[selection[0]]
            self.group_widgets["name_var"].set(grp.get("name", ""))
            items = grp.get("items", [])
            
            if self.use_ctk:
                self.group_widgets["items"].delete("0.0", "end")
                self.group_widgets["items"].insert("0.0", "\n".join(items))
            else:
                self.group_widgets["items"].delete("1.0", "end")
                self.group_widgets["items"].insert("1.0", "\n".join(items))
    
    def _pick_icon(self):
        """Open emoji picker for icon selection."""
        def on_select(emoji):
            self.editor_widgets["icon_var"].set(emoji)
        
        EmojiPicker(self.root, on_select, self.colors)
    
    def _add_action(self):
        """Add a new action."""
        name = ask_themed_string(self.root, "New Action", "Enter action name:", self.colors)
        if name and name not in self.options_data:
            self.options_data[name] = {
                "icon": "⚡",
                "prompt_type": "edit",
                "system_prompt": "",
                "task": "",
                "show_chat_window_instead_of_replace": False
            }
            self.action_listbox.insert("end", f"⚡ {name}")
            self.action_listbox.selection_clear(0, "end")
            self.action_listbox.selection_set("end")
            self._on_action_select(None)
    
    def _duplicate_action(self):
        """Duplicate selected action."""
        if not self.current_action:
            return
        
        new_name = f"{self.current_action}_copy"
        counter = 1
        while new_name in self.options_data:
            counter += 1
            new_name = f"{self.current_action}_copy{counter}"
        
        import copy
        self.options_data[new_name] = copy.deepcopy(self.options_data[self.current_action])
        
        icon = self.options_data[new_name].get("icon", "")
        self.action_listbox.insert("end", f"{icon} {new_name}")
    
    def _delete_action(self):
        """Delete selected action."""
        selection = self.action_listbox.curselection()
        if not selection or not self.current_action:
            return
        
        if messagebox.askyesno("Delete Action", f"Delete action '{self.current_action}'?", parent=self.root):
            del self.options_data[self.current_action]
            self.action_listbox.delete(selection[0])
            self.current_action = None
            if self.use_ctk:
                self.editor_widgets["name"].configure(text="(select an action)")
            else:
                self.editor_widgets["name"].configure(text="(select an action)")
    
    def _save_current_action(self):
        """Save the currently edited action."""
        if not self.current_action:
            return
        
        if self.use_ctk:
            system_prompt = self.editor_widgets["system_prompt"].get("0.0", "end").strip()
        else:
            system_prompt = self.editor_widgets["system_prompt"].get("1.0", "end").strip()
        
        self.options_data[self.current_action] = {
            "icon": self.editor_widgets["icon_var"].get(),
            "prompt_type": self.editor_widgets["prompt_type_var"].get(),
            "system_prompt": system_prompt,
            "task": self.editor_widgets["task_var"].get(),
            "show_chat_window_instead_of_replace": self.editor_widgets["show_chat_var"].get()
        }
        
        selection = self.action_listbox.curselection()
        if selection:
            icon = self.editor_widgets["icon_var"].get()
            self.action_listbox.delete(selection[0])
            self.action_listbox.insert(selection[0], f"{icon} {self.current_action}")
            self.action_listbox.selection_set(selection[0])
        
        if self.use_ctk:
            self.editor_widgets["save_status"].configure(
                text=f"✅ Saved '{self.current_action}'",
                text_color=self.colors.accent_green
            )
        else:
            self.editor_widgets["save_status"].configure(
                text=f"✅ Saved '{self.current_action}'",
                fg=self.colors.accent_green
            )
    
    def _add_modifier(self):
        """Add a new modifier."""
        key = ask_themed_string(self.root, "New Modifier", "Enter modifier key:", self.colors)
        if key:
            settings = self.options_data.setdefault("_settings", {})
            modifiers = settings.setdefault("modifiers", [])
            modifiers.append({
                "key": key,
                "icon": "🔧",
                "label": key.title(),
                "tooltip": "",
                "injection": "",
                "forces_chat_window": False
            })
            self.modifier_listbox.insert("end", f"🔧 {key.title()}")
    
    def _delete_modifier(self):
        """Delete selected modifier."""
        selection = self.modifier_listbox.curselection()
        if not selection:
            return
        
        settings = self.options_data.get("_settings", {})
        modifiers = settings.get("modifiers", [])
        
        if selection[0] < len(modifiers):
            if messagebox.askyesno("Delete Modifier", "Delete this modifier?", parent=self.root):
                del modifiers[selection[0]]
                self.modifier_listbox.delete(selection[0])
    
    def _save_current_modifier(self):
        """Save the currently edited modifier."""
        selection = self.modifier_listbox.curselection()
        if not selection:
            return
        
        settings = self.options_data.get("_settings", {})
        modifiers = settings.get("modifiers", [])
        
        if selection[0] < len(modifiers):
            if self.use_ctk:
                injection = self.modifier_widgets["injection"].get("0.0", "end").strip()
            else:
                injection = self.modifier_widgets["injection"].get("1.0", "end").strip()
            
            modifiers[selection[0]] = {
                "key": self.modifier_widgets["key_var"].get(),
                "icon": self.modifier_widgets["icon_var"].get(),
                "label": self.modifier_widgets["label_var"].get(),
                "tooltip": self.modifier_widgets["tooltip_var"].get(),
                "injection": injection,
                "forces_chat_window": self.modifier_widgets["forces_chat_var"].get()
            }
            
            icon = self.modifier_widgets["icon_var"].get()
            label = self.modifier_widgets["label_var"].get()
            self.modifier_listbox.delete(selection[0])
            self.modifier_listbox.insert(selection[0], f"{icon} {label}")
            self.modifier_listbox.selection_set(selection[0])
    
    def _add_group(self):
        """Add a new group."""
        name = ask_themed_string(self.root, "New Group", "Enter group name:", self.colors)
        if name:
            settings = self.options_data.setdefault("_settings", {})
            groups = settings.setdefault("popup_groups", [])
            groups.append({
                "name": name,
                "items": []
            })
            self.group_listbox.insert("end", name)
    
    def _delete_group(self):
        """Delete selected group."""
        selection = self.group_listbox.curselection()
        if not selection:
            return
        
        settings = self.options_data.get("_settings", {})
        groups = settings.get("popup_groups", [])
        
        if selection[0] < len(groups):
            if messagebox.askyesno("Delete Group", "Delete this group?", parent=self.root):
                del groups[selection[0]]
                self.group_listbox.delete(selection[0])
    
    def _save_current_group(self):
        """Save the currently edited group."""
        selection = self.group_listbox.curselection()
        if not selection:
            return
        
        settings = self.options_data.get("_settings", {})
        groups = settings.get("popup_groups", [])
        
        if selection[0] < len(groups):
            if self.use_ctk:
                items_text = self.group_widgets["items"].get("0.0", "end").strip()
            else:
                items_text = self.group_widgets["items"].get("1.0", "end").strip()
            items = [item.strip() for item in items_text.split("\n") if item.strip()]
            
            groups[selection[0]] = {
                "name": self.group_widgets["name_var"].get(),
                "items": items
            }
            
            name = self.group_widgets["name_var"].get()
            self.group_listbox.delete(selection[0])
            self.group_listbox.insert(selection[0], name)
            self.group_listbox.selection_set(selection[0])
    
    def _create_button_bar(self, parent):
        """Create the bottom button bar."""
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent") if self.use_ctk else tk.Frame(parent, bg=self.colors.bg)
        btn_frame.pack(fill="x", pady=(10, 0))
        
        if self.use_ctk:
            ctk.CTkButton(
                btn_frame, text="💾 Save All", font=get_ctk_font(14),
                width=140, height=42, **get_ctk_button_colors(self.colors, "success"),
                command=self._save_all
            ).pack(side="left", padx=6)
            
            ctk.CTkButton(
                btn_frame, text="Cancel", font=get_ctk_font(14),
                width=120, height=42, **get_ctk_button_colors(self.colors, "secondary"),
                command=self._close
            ).pack(side="left", padx=6)
            
            self.status_label = ctk.CTkLabel(
                btn_frame, text="", font=get_ctk_font(13),
                text_color=self.colors.accent_green
            )
        else:
            tk.Button(btn_frame, text="💾 Save All", font=("Segoe UI", 11),
                     bg=self.colors.accent_green, fg="#ffffff",
                     command=self._save_all).pack(side="left", padx=5)
            tk.Button(btn_frame, text="Cancel", font=("Segoe UI", 11),
                     bg=self.colors.surface1, fg=self.colors.fg,
                     command=self._close).pack(side="left", padx=5)
            self.status_label = tk.Label(btn_frame, text="", font=("Segoe UI", 10),
                                        bg=self.colors.bg, fg=self.colors.accent_green)
        self.status_label.pack(side="left", padx=20)
    
    def _save_all(self):
        """Save all options to file."""
        # Save settings from widgets
        if hasattr(self, 'settings_widgets'):
            settings = self.options_data.setdefault("_settings", {})
            for key, (widget_type, widget) in self.settings_widgets.items():
                if widget_type == "entry":
                    settings[key] = widget.get()
                elif widget_type == "text":
                    if self.use_ctk:
                        settings[key] = widget.get("0.0", "end").strip()
                    else:
                        settings[key] = widget.get("1.0", "end").strip()
                elif widget_type == "int":
                    settings[key] = widget.get()
                elif widget_type == "bool":
                    settings[key] = widget.get()
        
        # Save to file
        if save_options(self.options_data):
            if self.use_ctk:
                self.status_label.configure(text="✅ All options saved!", text_color=self.colors.accent_green)
            else:
                self.status_label.configure(text="✅ All options saved!", fg=self.colors.accent_green)
            
            # Reload options in text_edit_tool if possible
            try:
                from .text_edit_tool import reload_options
                reload_options()
                print("[PromptEditor] TextEditTool options hot-reloaded")
            except (ImportError, AttributeError) as e:
                print(f"[PromptEditor] Could not hot-reload options: {e}")
            
            # Close after brief delay
            self.root.after(1000, self._close)
        else:
            if self.use_ctk:
                self.status_label.configure(text="❌ Failed to save", text_color=self.colors.accent_red)
            else:
                self.status_label.configure(text="❌ Failed to save", fg=self.colors.accent_red)
    
    def _close(self):
        """Close the prompt editor window."""
        self._destroyed = True
        unregister_window(self.window_tag)
        try:
            if self.root:
                self.root.destroy()
        except tk.TclError:
            pass
        self.root = None


class AttachedPromptEditorWindow:
    """
    Prompt editor window as Toplevel attached to GUICoordinator's root.
    Used for centralized GUI threading.
    """
    
    def __init__(self, parent_root):
        self.parent_root = parent_root
        # Run directly on GUI thread as a child window
        editor = PromptEditorWindow(master=parent_root)
        editor.show()


def create_attached_prompt_editor_window(parent_root):
    """Create a prompt editor window (called on GUI thread)."""
    AttachedPromptEditorWindow(parent_root)


def show_prompt_editor():
    """Show prompt editor window - can be called from any thread."""
    def run():
        editor = PromptEditorWindow()
        editor.show()
    
    threading.Thread(target=run, daemon=True).start()