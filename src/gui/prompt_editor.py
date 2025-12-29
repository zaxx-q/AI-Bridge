#!/usr/bin/env python3
"""
Prompt Editor Window for AI Bridge

Provides a GUI for editing text_edit_tool_options.json without opening the file directly.
Features:
- Action list with add/delete/duplicate
- Action editor (icon, prompt_type, system_prompt, task)
- Settings editor for _settings object
- Modifier and group management
"""

import json
import os
import time
import shutil
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Dict, Optional, List, Callable, Any
from pathlib import Path

from .themes import ThemeRegistry, ThemeColors, get_colors
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
# Emoji Picker (Simple)
# =============================================================================

COMMON_EMOJIS = [
    "💡", "🧒", "🤙", "📋", "🔑", "✏", "✨", "📝", "🔄", "💼",
    "😊", "😎", "✂", "📊", "→", "💬", "(◕‿◕)", "⚡", "❓",
    "🎨", "📖", "🔧", "⚙️", "🔍", "💾", "📁", "✅", "❌", "⭐",
    "🚀", "💪", "🎯", "📌", "🔔", "💡", "🎉", "👍", "👎", "🤔"
]


class EmojiPicker(tk.Toplevel):
    """Simple emoji picker popup - 1.5x larger for better usability."""
    
    def __init__(self, parent, callback: Callable[[str], None], colors: ThemeColors):
        super().__init__(parent)
        self.callback = callback
        self.colors = colors
        
        self.title("Pick Icon")
        self.geometry("450x300")  # 1.5x larger
        self.configure(bg=colors.bg)
        self.transient(parent)
        self.grab_set()
        
        # Grid of emojis
        frame = tk.Frame(self, bg=colors.bg)
        frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        cols = 10  # More columns for larger window
        for i, emoji in enumerate(COMMON_EMOJIS):
            row = i // cols
            col = i % cols
            btn = tk.Label(
                frame,
                text=emoji,
                font=("Segoe UI", 18),  # Larger font
                bg=colors.surface0,
                fg=colors.fg,
                width=3,
                height=1,
                cursor="hand2"
            )
            btn.grid(row=row, column=col, padx=3, pady=3)
            btn.bind('<Button-1>', lambda e, em=emoji: self._select(em))
            btn.bind('<Enter>', lambda e, b=btn: b.config(bg=colors.surface1))
            btn.bind('<Leave>', lambda e, b=btn: b.config(bg=colors.surface0))
        
        # Custom entry
        custom_frame = tk.Frame(self, bg=colors.bg)
        custom_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        tk.Label(custom_frame, text="Custom:", font=("Segoe UI", 11),
                bg=colors.bg, fg=colors.fg).pack(side=tk.LEFT)
        
        self.custom_entry = tk.Entry(custom_frame, width=12, font=("Segoe UI", 14),
                                    bg=colors.input_bg, fg=colors.fg,
                                    insertbackground=colors.fg, relief=tk.FLAT,
                                    highlightbackground=colors.border, highlightthickness=1)
        self.custom_entry.pack(side=tk.LEFT, padx=8, ipady=3)
        
        tk.Button(custom_frame, text="Use", command=self._use_custom,
                 bg=colors.accent, fg="#ffffff", relief=tk.FLAT,
                 font=("Segoe UI", 10), padx=15, pady=3).pack(side=tk.LEFT)
    
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
# Themed Input Dialog
# =============================================================================

class ThemedInputDialog(tk.Toplevel):
    """Themed dialog for getting text input from user."""
    
    def __init__(self, parent, title: str, prompt: str, colors: ThemeColors):
        super().__init__(parent)
        self.colors = colors
        self.result = None
        
        self.title(title)
        self.geometry("400x160")
        self.configure(bg=colors.bg)
        self.transient(parent)
        self.grab_set()
        
        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 200
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 80
        self.geometry(f"+{x}+{y}")
        
        # Prompt label
        tk.Label(
            self,
            text=prompt,
            font=("Segoe UI", 11),
            bg=colors.bg,
            fg=colors.fg
        ).pack(pady=(20, 10), padx=20, anchor=tk.W)
        
        # Entry
        self.entry_var = tk.StringVar(master=self)
        self.entry = tk.Entry(
            self,
            textvariable=self.entry_var,
            font=("Segoe UI", 11),
            bg=colors.input_bg,
            fg=colors.fg,
            insertbackground=colors.fg,
            relief=tk.FLAT,
            highlightbackground=colors.border,
            highlightthickness=1,
            width=40
        )
        self.entry.pack(padx=20, ipady=6)
        self.entry.focus_set()
        
        # Buttons
        btn_frame = tk.Frame(self, bg=colors.bg)
        btn_frame.pack(pady=20)
        
        tk.Button(
            btn_frame,
            text="OK",
            font=("Segoe UI", 10),
            bg=colors.accent,
            fg="#ffffff",
            relief=tk.FLAT,
            padx=20,
            pady=5,
            command=self._ok
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="Cancel",
            font=("Segoe UI", 10),
            bg=colors.surface1,
            fg=colors.fg,
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._cancel
        ).pack(side=tk.LEFT, padx=5)
        
        # Bindings
        self.entry.bind('<Return>', lambda e: self._ok())
        self.bind('<Escape>', lambda e: self._cancel())
        
        # Wait for window to close
        self.protocol("WM_DELETE_WINDOW", self._cancel)
    
    def _ok(self):
        """Accept the input."""
        self.result = self.entry_var.get().strip()
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
# Prompt Editor Window
# =============================================================================

class PromptEditorWindow:
    """
    Standalone prompt editor window that creates its own Tk root.
    Used when launching from non-GUI contexts.
    """
    
    def __init__(self):
        self.window_id = get_next_window_id()
        self.window_tag = f"prompt_editor_{self.window_id}"
        
        self.colors = get_colors()
        self.root: Optional[tk.Tk] = None
        self._destroyed = False
        
        # Data
        self.options_data: Dict = {}
        self.current_action: Optional[str] = None
        
        # Widget references
        self.action_listbox: Optional[tk.Listbox] = None
        self.editor_widgets: Dict[str, Any] = {}
    
    def show(self):
        """Create and show the prompt editor window."""
        # Load current options
        self.options_data = load_options()
        
        self.root = tk.Tk()
        self.root.title("AI Bridge Prompt Editor")
        self.root.geometry("1000x700")
        self.root.configure(bg=self.colors.bg)
        self.root.minsize(800, 500)
        
        # Position window
        offset = (self.window_id % 3) * 30
        self.root.geometry(f"+{80 + offset}+{80 + offset}")
        
        # Configure grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        
        # Title bar
        self._create_title_bar()
        
        # Main content
        self._create_main_content()
        
        # Button bar
        self._create_button_bar()
        
        # Register and bind
        register_window(self.window_tag)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.bind('<Escape>', lambda e: self._close())
        
        # Focus
        self.root.lift()
        self.root.focus_force()
        
        # Event loop
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
    
    def _create_title_bar(self):
        """Create the title bar."""
        title_frame = tk.Frame(self.root, bg=self.colors.bg)
        title_frame.grid(row=0, column=0, sticky=tk.EW, padx=20, pady=(15, 10))
        
        tk.Label(
            title_frame,
            text="✏️ Prompt Editor",
            font=("Segoe UI", 16, "bold"),
            bg=self.colors.bg,
            fg=self.colors.fg
        ).pack(side=tk.LEFT)
        
        tk.Label(
            title_frame,
            text="Edit text_edit_tool_options.json",
            font=("Segoe UI", 10),
            bg=self.colors.bg,
            fg=self.colors.blockquote
        ).pack(side=tk.LEFT, padx=(15, 0))
    
    def _create_main_content(self):
        """Create the main content area with notebook."""
        # Style for notebook
        style = ttk.Style(self.root)
        style.theme_use('clam')
        
        style.configure('TNotebook', background=self.colors.bg, borderwidth=0)
        style.configure('TNotebook.Tab',
                       background=self.colors.surface0,
                       foreground=self.colors.fg,
                       padding=[12, 6],
                       font=('Segoe UI', 10))
        style.map('TNotebook.Tab',
                 background=[('selected', self.colors.accent)],
                 foreground=[('selected', '#ffffff')])
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky=tk.NSEW, padx=20, pady=5)
        
        # Create tabs
        self._create_actions_tab()
        self._create_settings_tab()
        self._create_modifiers_tab()
        self._create_groups_tab()
    
    def _create_actions_tab(self):
        """Create the Actions editing tab."""
        frame = tk.Frame(self.notebook, bg=self.colors.bg)
        self.notebook.add(frame, text="Actions")
        
        # Configure grid
        frame.columnconfigure(0, weight=1, minsize=200)
        frame.columnconfigure(1, weight=3)
        frame.rowconfigure(0, weight=1)
        
        # Left panel: action list
        left_panel = tk.Frame(frame, bg=self.colors.bg)
        left_panel.grid(row=0, column=0, sticky=tk.NSEW, padx=(15, 10), pady=15)
        left_panel.rowconfigure(1, weight=1)
        left_panel.columnconfigure(0, weight=1)
        
        tk.Label(left_panel, text="Actions", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=0, column=0, sticky=tk.W, pady=(0, 10))
        
        # Listbox with scrollbar
        list_frame = tk.Frame(left_panel, bg=self.colors.bg)
        list_frame.grid(row=1, column=0, sticky=tk.NSEW)
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        
        self.action_listbox = tk.Listbox(
            list_frame,
            font=("Segoe UI", 10),
            bg=self.colors.input_bg,
            fg=self.colors.fg,
            selectbackground=self.colors.accent,
            selectforeground="#ffffff",
            relief=tk.FLAT,
            highlightbackground=self.colors.border,
            highlightthickness=1
        )
        self.action_listbox.grid(row=0, column=0, sticky=tk.NSEW)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                 command=self.action_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)
        self.action_listbox.configure(yscrollcommand=scrollbar.set)
        
        # Populate action list - include ALL actions, even those starting with _
        for name in sorted(self.options_data.keys()):
            if name == "_settings":
                continue  # Skip settings, it's not an action
            icon = self.options_data[name].get("icon", "")
            self.action_listbox.insert(tk.END, f"{icon} {name}")
        
        self.action_listbox.bind('<<ListboxSelect>>', self._on_action_select)
        
        # Action buttons
        btn_frame = tk.Frame(left_panel, bg=self.colors.bg)
        btn_frame.grid(row=2, column=0, sticky=tk.EW, pady=(10, 0))
        
        tk.Button(btn_frame, text="➕ Add", font=("Segoe UI", 9),
                 bg=self.colors.accent_green, fg="#ffffff",
                 relief=tk.FLAT, padx=8, pady=3,
                 command=self._add_action).pack(side=tk.LEFT, padx=2)
        
        tk.Button(btn_frame, text="📋 Duplicate", font=("Segoe UI", 9),
                 bg=self.colors.surface1, fg=self.colors.fg,
                 relief=tk.FLAT, padx=8, pady=3,
                 command=self._duplicate_action).pack(side=tk.LEFT, padx=2)
        
        tk.Button(btn_frame, text="🗑️ Delete", font=("Segoe UI", 9),
                 bg=self.colors.accent_red, fg="#ffffff",
                 relief=tk.FLAT, padx=8, pady=3,
                 command=self._delete_action).pack(side=tk.LEFT, padx=2)
        
        # Right panel: action editor
        right_panel = tk.Frame(frame, bg=self.colors.bg)
        right_panel.grid(row=0, column=1, sticky=tk.NSEW, padx=(10, 15), pady=15)
        right_panel.columnconfigure(1, weight=1)
        right_panel.rowconfigure(4, weight=1)
        right_panel.rowconfigure(6, weight=1)
        
        tk.Label(right_panel, text="Edit Action", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        
        # Action name (read-only)
        tk.Label(right_panel, text="Name:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=1, column=0, sticky=tk.W, pady=5)
        
        self.editor_widgets["name"] = tk.Label(
            right_panel, text="(select an action)",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors.bg, fg=self.colors.fg
        )
        self.editor_widgets["name"].grid(row=1, column=1, sticky=tk.W, padx=(10, 0))
        
        # Icon
        tk.Label(right_panel, text="Icon:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=2, column=0, sticky=tk.W, pady=5)
        
        icon_frame = tk.Frame(right_panel, bg=self.colors.bg)
        icon_frame.grid(row=2, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        self.editor_widgets["icon_var"] = tk.StringVar(master=self.root)
        self.editor_widgets["icon_entry"] = tk.Entry(
            icon_frame, textvariable=self.editor_widgets["icon_var"],
            font=("Segoe UI", 12), width=5,
            bg=self.colors.input_bg, fg=self.colors.fg,
            relief=tk.FLAT, highlightbackground=self.colors.border,
            highlightthickness=1
        )
        self.editor_widgets["icon_entry"].pack(side=tk.LEFT, ipady=3)
        
        tk.Button(icon_frame, text="Pick...", font=("Segoe UI", 9),
                 bg=self.colors.surface1, fg=self.colors.fg,
                 relief=tk.FLAT, padx=8,
                 command=self._pick_icon).pack(side=tk.LEFT, padx=(5, 0))
        
        # Prompt type
        tk.Label(right_panel, text="Type:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=3, column=0, sticky=tk.W, pady=5)
        
        self.editor_widgets["prompt_type_var"] = tk.StringVar(master=self.root, value="edit")
        type_combo = ttk.Combobox(right_panel,
                                 textvariable=self.editor_widgets["prompt_type_var"],
                                 values=["edit", "general"],
                                 state="readonly", width=15)
        type_combo.grid(row=3, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        self.editor_widgets["prompt_type"] = type_combo
        
        # System prompt
        tk.Label(right_panel, text="System Prompt:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=4, column=0, sticky=tk.NW, pady=5)
        
        sys_frame = tk.Frame(right_panel, bg=self.colors.bg)
        sys_frame.grid(row=4, column=1, sticky=tk.NSEW, pady=5, padx=(10, 0))
        sys_frame.rowconfigure(0, weight=1)
        sys_frame.columnconfigure(0, weight=1)
        
        self.editor_widgets["system_prompt"] = tk.Text(
            sys_frame, font=("Consolas", 10), height=6,
            bg=self.colors.input_bg, fg=self.colors.fg,
            insertbackground=self.colors.fg,
            relief=tk.FLAT, highlightbackground=self.colors.border,
            highlightthickness=1, wrap=tk.WORD
        )
        self.editor_widgets["system_prompt"].grid(row=0, column=0, sticky=tk.NSEW)
        
        sys_scroll = ttk.Scrollbar(sys_frame, orient=tk.VERTICAL,
                                  command=self.editor_widgets["system_prompt"].yview)
        sys_scroll.grid(row=0, column=1, sticky=tk.NS)
        self.editor_widgets["system_prompt"].configure(yscrollcommand=sys_scroll.set)
        
        # Task
        tk.Label(right_panel, text="Task:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=5, column=0, sticky=tk.W, pady=5)
        
        self.editor_widgets["task_var"] = tk.StringVar(master=self.root)
        task_entry = tk.Entry(
            right_panel, textvariable=self.editor_widgets["task_var"],
            font=("Segoe UI", 10),
            bg=self.colors.input_bg, fg=self.colors.fg,
            insertbackground=self.colors.fg,
            relief=tk.FLAT, highlightbackground=self.colors.border,
            highlightthickness=1
        )
        task_entry.grid(row=5, column=1, sticky=tk.EW, pady=5, padx=(10, 0), ipady=5)
        self.editor_widgets["task"] = task_entry
        
        # Show in chat window toggle
        tk.Label(right_panel, text="Show in chat:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=6, column=0, sticky=tk.NW, pady=5)
        
        self.editor_widgets["show_chat_var"] = tk.BooleanVar(master=self.root)
        show_check = tk.Checkbutton(
            right_panel, text="Show response in chat window instead of replacing text",
            variable=self.editor_widgets["show_chat_var"],
            font=("Segoe UI", 10),
            bg=self.colors.bg, fg=self.colors.fg,
            selectcolor=self.colors.input_bg,
            activebackground=self.colors.bg,
            activeforeground=self.colors.fg
        )
        show_check.grid(row=6, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        self.editor_widgets["show_chat"] = show_check
        
        # Save action button
        save_btn_frame = tk.Frame(right_panel, bg=self.colors.bg)
        save_btn_frame.grid(row=7, column=0, columnspan=2, sticky=tk.W, pady=(15, 0))
        
        tk.Button(save_btn_frame, text="💾 Save Action", font=("Segoe UI", 10),
                 bg=self.colors.accent_green, fg="#ffffff",
                 relief=tk.FLAT, padx=15, pady=5,
                 command=self._save_current_action).pack(side=tk.LEFT)
        
        self.editor_widgets["save_status"] = tk.Label(
            save_btn_frame, text="", font=("Segoe UI", 9),
            bg=self.colors.bg, fg=self.colors.accent_green
        )
        self.editor_widgets["save_status"].pack(side=tk.LEFT, padx=15)
    
    def _create_settings_tab(self):
        """Create the Settings tab for _settings object."""
        frame = tk.Frame(self.notebook, bg=self.colors.bg)
        self.notebook.add(frame, text="Settings")
        
        # Scrollable canvas
        canvas = tk.Canvas(frame, bg=self.colors.bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.colors.bg)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=15, pady=15)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Get settings
        settings = self.options_data.get("_settings", {})
        row = 0
        
        self.settings_widgets = {}
        
        # Instructions
        tk.Label(scrollable_frame, text="Global Settings", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        row += 1
        
        # Text fields from settings
        text_fields = [
            ("chat_system_instruction", "Chat System Instruction"),
            ("chat_window_system_instruction", "Chat Window System Instruction"),
            ("base_output_rules", "Base Output Rules"),
            ("base_output_rules_general", "Base Output Rules (General)"),
            ("text_delimiter", "Text Delimiter"),
            ("text_delimiter_close", "Text Delimiter Close"),
            ("custom_task_template", "Custom Task Template"),
            ("ask_task_template", "Ask Task Template"),
        ]
        
        for key, label in text_fields:
            tk.Label(scrollable_frame, text=f"{label}:", font=("Segoe UI", 10),
                    bg=self.colors.bg, fg=self.colors.fg).grid(
                    row=row, column=0, sticky=tk.NW, pady=5, padx=(0, 10))
            
            if key in ["text_delimiter", "text_delimiter_close", 
                       "custom_task_template", "ask_task_template"]:
                # Single-line entry
                var = tk.StringVar(master=scrollable_frame, value=settings.get(key, ""))
                entry = tk.Entry(scrollable_frame, textvariable=var,
                               font=("Segoe UI", 10), width=60,
                               bg=self.colors.input_bg, fg=self.colors.fg,
                               relief=tk.FLAT, highlightbackground=self.colors.border,
                               highlightthickness=1)
                entry.grid(row=row, column=1, sticky=tk.W, pady=5, ipady=4)
                self.settings_widgets[key] = ("entry", var)
            else:
                # Multi-line text
                text = tk.Text(scrollable_frame, font=("Consolas", 9),
                             height=4, width=60,
                             bg=self.colors.input_bg, fg=self.colors.fg,
                             relief=tk.FLAT, highlightbackground=self.colors.border,
                             highlightthickness=1, wrap=tk.WORD)
                text.insert("1.0", settings.get(key, ""))
                text.grid(row=row, column=1, sticky=tk.W, pady=5)
                self.settings_widgets[key] = ("text", text)
            
            row += 1
        
        # Numeric settings
        tk.Label(scrollable_frame, text="Popup Settings", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=2, sticky=tk.W, pady=(20, 10))
        row += 1
        
        # Items per page
        tk.Label(scrollable_frame, text="Items per page:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        
        items_var = tk.IntVar(master=scrollable_frame, value=settings.get("popup_items_per_page", 6))
        items_spin = ttk.Spinbox(scrollable_frame, textvariable=items_var,
                                from_=3, to=20, width=10)
        items_spin.grid(row=row, column=1, sticky=tk.W, pady=5)
        self.settings_widgets["popup_items_per_page"] = ("int", items_var)
        row += 1
        
        # Use groups
        tk.Label(scrollable_frame, text="Use groups:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        
        groups_var = tk.BooleanVar(master=scrollable_frame, value=settings.get("popup_use_groups", True))
        groups_check = tk.Checkbutton(scrollable_frame, variable=groups_var,
                                     bg=self.colors.bg, selectcolor=self.colors.input_bg)
        groups_check.grid(row=row, column=1, sticky=tk.W, pady=5)
        self.settings_widgets["popup_use_groups"] = ("bool", groups_var)
    
    def _create_modifiers_tab(self):
        """Create the Modifiers editing tab."""
        frame = tk.Frame(self.notebook, bg=self.colors.bg)
        self.notebook.add(frame, text="Modifiers")
        
        frame.columnconfigure(0, weight=1, minsize=200)
        frame.columnconfigure(1, weight=2)
        frame.rowconfigure(0, weight=1)
        
        # Left: modifier list
        left_panel = tk.Frame(frame, bg=self.colors.bg)
        left_panel.grid(row=0, column=0, sticky=tk.NSEW, padx=(15, 10), pady=15)
        left_panel.rowconfigure(1, weight=1)
        left_panel.columnconfigure(0, weight=1)
        
        tk.Label(left_panel, text="Modifiers", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=0, column=0, sticky=tk.W, pady=(0, 10))
        
        list_frame = tk.Frame(left_panel, bg=self.colors.bg)
        list_frame.grid(row=1, column=0, sticky=tk.NSEW)
        
        self.modifier_listbox = tk.Listbox(
            list_frame,
            font=("Segoe UI", 10),
            bg=self.colors.input_bg,
            fg=self.colors.fg,
            selectbackground=self.colors.accent,
            selectforeground="#ffffff",
            relief=tk.FLAT,
            highlightbackground=self.colors.border,
            highlightthickness=1
        )
        self.modifier_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        mod_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                  command=self.modifier_listbox.yview)
        mod_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.modifier_listbox.configure(yscrollcommand=mod_scroll.set)
        
        # Populate modifiers
        settings = self.options_data.get("_settings", {})
        modifiers = settings.get("modifiers", [])
        for mod in modifiers:
            self.modifier_listbox.insert(tk.END, f"{mod.get('icon', '')} {mod.get('label', mod.get('key', ''))}")
        
        self.modifier_listbox.bind('<<ListboxSelect>>', self._on_modifier_select)
        
        # Buttons
        btn_frame = tk.Frame(left_panel, bg=self.colors.bg)
        btn_frame.grid(row=2, column=0, sticky=tk.EW, pady=(10, 0))
        
        tk.Button(btn_frame, text="➕ Add", font=("Segoe UI", 9),
                 bg=self.colors.accent_green, fg="#ffffff",
                 relief=tk.FLAT, padx=8, pady=3,
                 command=self._add_modifier).pack(side=tk.LEFT, padx=2)
        
        tk.Button(btn_frame, text="🗑️ Delete", font=("Segoe UI", 9),
                 bg=self.colors.accent_red, fg="#ffffff",
                 relief=tk.FLAT, padx=8, pady=3,
                 command=self._delete_modifier).pack(side=tk.LEFT, padx=2)
        
        # Right: modifier editor
        right_panel = tk.Frame(frame, bg=self.colors.bg)
        right_panel.grid(row=0, column=1, sticky=tk.NSEW, padx=(10, 15), pady=15)
        right_panel.columnconfigure(1, weight=1)
        
        tk.Label(right_panel, text="Edit Modifier", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        
        self.modifier_widgets = {}
        row = 1
        
        # Key
        tk.Label(right_panel, text="Key:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        self.modifier_widgets["key_var"] = tk.StringVar(master=self.root)
        tk.Entry(right_panel, textvariable=self.modifier_widgets["key_var"],
                font=("Segoe UI", 10), width=20,
                bg=self.colors.input_bg, fg=self.colors.fg,
                relief=tk.FLAT, highlightbackground=self.colors.border,
                highlightthickness=1).grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0), ipady=4)
        row += 1
        
        # Icon
        tk.Label(right_panel, text="Icon:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        self.modifier_widgets["icon_var"] = tk.StringVar(master=self.root)
        tk.Entry(right_panel, textvariable=self.modifier_widgets["icon_var"],
                font=("Segoe UI", 12), width=5,
                bg=self.colors.input_bg, fg=self.colors.fg,
                relief=tk.FLAT, highlightbackground=self.colors.border,
                highlightthickness=1).grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0), ipady=3)
        row += 1
        
        # Label
        tk.Label(right_panel, text="Label:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        self.modifier_widgets["label_var"] = tk.StringVar(master=self.root)
        tk.Entry(right_panel, textvariable=self.modifier_widgets["label_var"],
                font=("Segoe UI", 10), width=20,
                bg=self.colors.input_bg, fg=self.colors.fg,
                relief=tk.FLAT, highlightbackground=self.colors.border,
                highlightthickness=1).grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0), ipady=4)
        row += 1
        
        # Tooltip
        tk.Label(right_panel, text="Tooltip:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        self.modifier_widgets["tooltip_var"] = tk.StringVar(master=self.root)
        tk.Entry(right_panel, textvariable=self.modifier_widgets["tooltip_var"],
                font=("Segoe UI", 10), width=40,
                bg=self.colors.input_bg, fg=self.colors.fg,
                relief=tk.FLAT, highlightbackground=self.colors.border,
                highlightthickness=1).grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0), ipady=4)
        row += 1
        
        # Injection
        tk.Label(right_panel, text="Injection:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.NW, pady=5)
        self.modifier_widgets["injection"] = tk.Text(
            right_panel, font=("Consolas", 9), height=4, width=50,
            bg=self.colors.input_bg, fg=self.colors.fg,
            relief=tk.FLAT, highlightbackground=self.colors.border,
            highlightthickness=1, wrap=tk.WORD
        )
        self.modifier_widgets["injection"].grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        row += 1
        
        # Forces chat window
        tk.Label(right_panel, text="Forces chat:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        self.modifier_widgets["forces_chat_var"] = tk.BooleanVar(master=self.root)
        tk.Checkbutton(right_panel, variable=self.modifier_widgets["forces_chat_var"],
                      bg=self.colors.bg, selectcolor=self.colors.input_bg).grid(
                      row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        row += 1
        
        # Save button
        tk.Button(right_panel, text="💾 Save Modifier", font=("Segoe UI", 10),
                 bg=self.colors.accent_green, fg="#ffffff",
                 relief=tk.FLAT, padx=15, pady=5,
                 command=self._save_current_modifier).grid(
                 row=row, column=0, columnspan=2, sticky=tk.W, pady=(15, 0))
    
    def _create_groups_tab(self):
        """Create the Groups editing tab."""
        frame = tk.Frame(self.notebook, bg=self.colors.bg)
        self.notebook.add(frame, text="Groups")
        
        frame.columnconfigure(0, weight=1, minsize=200)
        frame.columnconfigure(1, weight=2)
        frame.rowconfigure(0, weight=1)
        
        # Left: group list
        left_panel = tk.Frame(frame, bg=self.colors.bg)
        left_panel.grid(row=0, column=0, sticky=tk.NSEW, padx=(15, 10), pady=15)
        left_panel.rowconfigure(1, weight=1)
        left_panel.columnconfigure(0, weight=1)
        
        tk.Label(left_panel, text="Groups", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=0, column=0, sticky=tk.W, pady=(0, 10))
        
        list_frame = tk.Frame(left_panel, bg=self.colors.bg)
        list_frame.grid(row=1, column=0, sticky=tk.NSEW)
        
        self.group_listbox = tk.Listbox(
            list_frame,
            font=("Segoe UI", 10),
            bg=self.colors.input_bg,
            fg=self.colors.fg,
            selectbackground=self.colors.accent,
            selectforeground="#ffffff",
            relief=tk.FLAT,
            highlightbackground=self.colors.border,
            highlightthickness=1
        )
        self.group_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        grp_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                  command=self.group_listbox.yview)
        grp_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.group_listbox.configure(yscrollcommand=grp_scroll.set)
        
        # Populate groups
        settings = self.options_data.get("_settings", {})
        groups = settings.get("popup_groups", [])
        for grp in groups:
            self.group_listbox.insert(tk.END, grp.get("name", "Unnamed"))
        
        self.group_listbox.bind('<<ListboxSelect>>', self._on_group_select)
        
        # Buttons
        btn_frame = tk.Frame(left_panel, bg=self.colors.bg)
        btn_frame.grid(row=2, column=0, sticky=tk.EW, pady=(10, 0))
        
        tk.Button(btn_frame, text="➕ Add", font=("Segoe UI", 9),
                 bg=self.colors.accent_green, fg="#ffffff",
                 relief=tk.FLAT, padx=8, pady=3,
                 command=self._add_group).pack(side=tk.LEFT, padx=2)
        
        tk.Button(btn_frame, text="🗑️ Delete", font=("Segoe UI", 9),
                 bg=self.colors.accent_red, fg="#ffffff",
                 relief=tk.FLAT, padx=8, pady=3,
                 command=self._delete_group).pack(side=tk.LEFT, padx=2)
        
        # Right: group editor
        right_panel = tk.Frame(frame, bg=self.colors.bg)
        right_panel.grid(row=0, column=1, sticky=tk.NSEW, padx=(10, 15), pady=15)
        right_panel.columnconfigure(1, weight=1)
        right_panel.rowconfigure(2, weight=1)
        
        tk.Label(right_panel, text="Edit Group", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        
        self.group_widgets = {}
        
        # Name
        tk.Label(right_panel, text="Name:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=1, column=0, sticky=tk.W, pady=5)
        self.group_widgets["name_var"] = tk.StringVar(master=self.root)
        tk.Entry(right_panel, textvariable=self.group_widgets["name_var"],
                font=("Segoe UI", 10), width=25,
                bg=self.colors.input_bg, fg=self.colors.fg,
                relief=tk.FLAT, highlightbackground=self.colors.border,
                highlightthickness=1).grid(row=1, column=1, sticky=tk.W, pady=5, padx=(10, 0), ipady=4)
        
        # Items (comma-separated list of action names)
        tk.Label(right_panel, text="Items:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=2, column=0, sticky=tk.NW, pady=5)
        
        items_frame = tk.Frame(right_panel, bg=self.colors.bg)
        items_frame.grid(row=2, column=1, sticky=tk.NSEW, pady=5, padx=(10, 0))
        items_frame.rowconfigure(0, weight=1)
        items_frame.columnconfigure(0, weight=1)
        
        self.group_widgets["items"] = tk.Text(
            items_frame, font=("Segoe UI", 10), height=8,
            bg=self.colors.input_bg, fg=self.colors.fg,
            relief=tk.FLAT, highlightbackground=self.colors.border,
            highlightthickness=1, wrap=tk.WORD
        )
        self.group_widgets["items"].grid(row=0, column=0, sticky=tk.NSEW)
        
        items_scroll = ttk.Scrollbar(items_frame, orient=tk.VERTICAL,
                                    command=self.group_widgets["items"].yview)
        items_scroll.grid(row=0, column=1, sticky=tk.NS)
        self.group_widgets["items"].configure(yscrollcommand=items_scroll.set)
        
        tk.Label(right_panel, text="(One action name per line)",
                font=("Segoe UI", 9), bg=self.colors.bg,
                fg=self.colors.blockquote).grid(
                row=3, column=1, sticky=tk.W, padx=(10, 0))
        
        # Save button
        tk.Button(right_panel, text="💾 Save Group", font=("Segoe UI", 10),
                 bg=self.colors.accent_green, fg="#ffffff",
                 relief=tk.FLAT, padx=15, pady=5,
                 command=self._save_current_group).grid(
                 row=4, column=0, columnspan=2, sticky=tk.W, pady=(15, 0))
    
    # Event handlers
    
    def _on_action_select(self, event):
        """Handle action selection."""
        selection = self.action_listbox.curselection()
        if not selection:
            return
        
        # Parse action name from display text (remove icon prefix)
        display_text = self.action_listbox.get(selection[0])
        parts = display_text.split(" ", 1)
        action_name = parts[1] if len(parts) > 1 else parts[0]
        
        self.current_action = action_name
        action_data = self.options_data.get(action_name, {})
        
        # Populate editor
        self.editor_widgets["name"].configure(text=action_name)
        self.editor_widgets["icon_var"].set(action_data.get("icon", ""))
        self.editor_widgets["prompt_type_var"].set(action_data.get("prompt_type", "edit"))
        
        self.editor_widgets["system_prompt"].delete("1.0", tk.END)
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
            self.modifier_widgets["injection"].delete("1.0", tk.END)
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
            self.group_widgets["items"].delete("1.0", tk.END)
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
            self.action_listbox.insert(tk.END, f"⚡ {name}")
            # Select the new action
            self.action_listbox.selection_clear(0, tk.END)
            self.action_listbox.selection_set(tk.END)
            self._on_action_select(None)
    
    def _duplicate_action(self):
        """Duplicate selected action."""
        selection = self.action_listbox.curselection()
        if not selection:
            return
        
        if not self.current_action:
            return
        
        new_name = f"{self.current_action}_copy"
        counter = 1
        while new_name in self.options_data:
            counter += 1
            new_name = f"{self.current_action}_copy{counter}"
        
        # Deep copy the action
        import copy
        self.options_data[new_name] = copy.deepcopy(self.options_data[self.current_action])
        
        icon = self.options_data[new_name].get("icon", "")
        self.action_listbox.insert(tk.END, f"{icon} {new_name}")
    
    def _delete_action(self):
        """Delete selected action."""
        selection = self.action_listbox.curselection()
        if not selection or not self.current_action:
            return
        
        if messagebox.askyesno("Delete Action", 
                              f"Delete action '{self.current_action}'?",
                              parent=self.root):
            del self.options_data[self.current_action]
            self.action_listbox.delete(selection[0])
            self.current_action = None
            self.editor_widgets["name"].configure(text="(select an action)")
    
    def _save_current_action(self):
        """Save the currently edited action."""
        if not self.current_action:
            return
        
        self.options_data[self.current_action] = {
            "icon": self.editor_widgets["icon_var"].get(),
            "prompt_type": self.editor_widgets["prompt_type_var"].get(),
            "system_prompt": self.editor_widgets["system_prompt"].get("1.0", tk.END).strip(),
            "task": self.editor_widgets["task_var"].get(),
            "show_chat_window_instead_of_replace": self.editor_widgets["show_chat_var"].get()
        }
        
        # Update listbox
        selection = self.action_listbox.curselection()
        if selection:
            icon = self.editor_widgets["icon_var"].get()
            self.action_listbox.delete(selection[0])
            self.action_listbox.insert(selection[0], f"{icon} {self.current_action}")
            self.action_listbox.selection_set(selection[0])
        
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
            self.modifier_listbox.insert(tk.END, f"🔧 {key.title()}")
    
    def _delete_modifier(self):
        """Delete selected modifier."""
        selection = self.modifier_listbox.curselection()
        if not selection:
            return
        
        settings = self.options_data.get("_settings", {})
        modifiers = settings.get("modifiers", [])
        
        if selection[0] < len(modifiers):
            if messagebox.askyesno("Delete Modifier", "Delete this modifier?",
                                  parent=self.root):
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
            modifiers[selection[0]] = {
                "key": self.modifier_widgets["key_var"].get(),
                "icon": self.modifier_widgets["icon_var"].get(),
                "label": self.modifier_widgets["label_var"].get(),
                "tooltip": self.modifier_widgets["tooltip_var"].get(),
                "injection": self.modifier_widgets["injection"].get("1.0", tk.END).strip(),
                "forces_chat_window": self.modifier_widgets["forces_chat_var"].get()
            }
            
            # Update listbox
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
            self.group_listbox.insert(tk.END, name)
    
    def _delete_group(self):
        """Delete selected group."""
        selection = self.group_listbox.curselection()
        if not selection:
            return
        
        settings = self.options_data.get("_settings", {})
        groups = settings.get("popup_groups", [])
        
        if selection[0] < len(groups):
            if messagebox.askyesno("Delete Group", "Delete this group?",
                                  parent=self.root):
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
            items_text = self.group_widgets["items"].get("1.0", tk.END).strip()
            items = [item.strip() for item in items_text.split("\n") if item.strip()]
            
            groups[selection[0]] = {
                "name": self.group_widgets["name_var"].get(),
                "items": items
            }
            
            # Update listbox
            name = self.group_widgets["name_var"].get()
            self.group_listbox.delete(selection[0])
            self.group_listbox.insert(selection[0], name)
            self.group_listbox.selection_set(selection[0])
    
    def _create_button_bar(self):
        """Create the bottom button bar."""
        btn_frame = tk.Frame(self.root, bg=self.colors.bg)
        btn_frame.grid(row=2, column=0, sticky=tk.EW, padx=20, pady=(10, 20))
        
        tk.Button(
            btn_frame,
            text="💾 Save All",
            font=("Segoe UI", 11),
            bg=self.colors.accent_green,
            fg="#ffffff",
            activebackground="#45a049",
            relief=tk.FLAT,
            padx=20,
            pady=8,
            command=self._save_all
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="Cancel",
            font=("Segoe UI", 11),
            bg=self.colors.surface1,
            fg=self.colors.fg,
            activebackground=self.colors.surface2,
            relief=tk.FLAT,
            padx=20,
            pady=8,
            command=self._close
        ).pack(side=tk.LEFT, padx=5)
        
        self.status_label = tk.Label(
            btn_frame,
            text="",
            font=("Segoe UI", 10),
            bg=self.colors.bg,
            fg=self.colors.accent_green
        )
        self.status_label.pack(side=tk.LEFT, padx=20)
    
    def _save_all(self):
        """Save all options to file."""
        # Save settings from widgets
        if hasattr(self, 'settings_widgets'):
            settings = self.options_data.setdefault("_settings", {})
            for key, (widget_type, widget) in self.settings_widgets.items():
                if widget_type == "entry":
                    settings[key] = widget.get()
                elif widget_type == "text":
                    settings[key] = widget.get("1.0", tk.END).strip()
                elif widget_type == "int":
                    settings[key] = widget.get()
                elif widget_type == "bool":
                    settings[key] = widget.get()
        
        # Save to file
        if save_options(self.options_data):
            self.status_label.configure(text="✅ All options saved!",
                                       fg=self.colors.accent_green)
            
            # Reload options in text_edit_tool if possible
            try:
                from . import text_edit_tool
                text_edit_tool.reload_options()
            except (ImportError, AttributeError):
                pass
            
            # Close after brief delay
            self.root.after(1000, self._close)
        else:
            self.status_label.configure(text="❌ Failed to save",
                                       fg=self.colors.accent_red)
    
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
    
    def __init__(self, parent_root: tk.Tk):
        self.parent_root = parent_root
        self.window_id = get_next_window_id()
        self.window_tag = f"attached_prompt_editor_{self.window_id}"
        
        # Create a standalone window since editor is complex
        def run_editor():
            editor = PromptEditorWindow()
            editor.show()
        
        # Run in thread to not block coordinator
        threading.Thread(target=run_editor, daemon=True).start()


def create_attached_prompt_editor_window(parent_root: tk.Tk):
    """Create a prompt editor window (called on GUI thread)."""
    AttachedPromptEditorWindow(parent_root)


def show_prompt_editor():
    """Show prompt editor window - can be called from any thread."""
    def run():
        editor = PromptEditorWindow()
        editor.show()
    
    threading.Thread(target=run, daemon=True).start()