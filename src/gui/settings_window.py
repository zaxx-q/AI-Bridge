#!/usr/bin/env python3
"""
Settings Window for AI Bridge

Provides a GUI for editing config.ini without opening the file directly.
Features:
- Tabbed interface for different config sections
- Theme selector with live preview
- Validation for fields like ports, hotkeys
- Save/Cancel with backup creation
"""

import os
import re
import time
import shutil
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Optional, List, Callable, Any
from pathlib import Path

from .themes import ThemeRegistry, ThemeColors, get_colors, list_themes
from .core import get_next_window_id, register_window, unregister_window


# =============================================================================
# Config Parser/Writer
# =============================================================================

class ConfigData:
    """
    Structured representation of config.ini data.
    Preserves comments and structure for round-trip editing.
    """
    
    def __init__(self):
        self.config: Dict[str, Any] = {}       # [config] section values
        self.endpoints: Dict[str, str] = {}    # [endpoints] section
        self.keys: Dict[str, List[str]] = {    # API key sections
            "custom": [],
            "openrouter": [],
            "google": []
        }
        self.raw_lines: List[str] = []         # Original lines for preservation
        self.comments: Dict[str, str] = {}     # Comments associated with keys


def parse_config_full(filepath: str = "config.ini") -> ConfigData:
    """
    Parse entire config file preserving structure and comments.
    
    Returns:
        ConfigData with all sections parsed
    """
    data = ConfigData()
    
    if not Path(filepath).exists():
        return data
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        data.raw_lines = lines
        current_section = None
        multiline_key = None
        multiline_value = []
        last_comment = ""
        
        for line in lines:
            raw_line = line.rstrip('\n\r')
            stripped = raw_line.strip()
            
            # Track comments
            if stripped.startswith('#'):
                last_comment = stripped
                continue
            
            if not stripped:
                last_comment = ""
                continue
            
            # Section header
            if stripped.startswith('[') and stripped.endswith(']'):
                if multiline_key and current_section == 'endpoints':
                    data.endpoints[multiline_key] = ' '.join(multiline_value)
                    multiline_key = None
                    multiline_value = []
                current_section = stripped[1:-1].lower()
                continue
            
            # Parse based on section
            if current_section == 'config':
                if '=' in stripped:
                    key, value = stripped.split('=', 1)
                    key = key.strip().lower()
                    value = _parse_value(value.strip())
                    data.config[key] = value
                    if last_comment:
                        data.comments[key] = last_comment
                    last_comment = ""
            
            elif current_section == 'endpoints':
                if '=' in stripped:
                    if multiline_key:
                        data.endpoints[multiline_key] = ' '.join(multiline_value)
                    endpoint_name, prompt = stripped.split('=', 1)
                    endpoint_name = endpoint_name.strip().lower()
                    prompt = prompt.strip()
                    # Remove quotes if present
                    if (prompt.startswith('"') and prompt.endswith('"')) or \
                       (prompt.startswith("'") and prompt.endswith("'")):
                        prompt = prompt[1:-1]
                    if prompt.endswith('\\'):
                        multiline_key = endpoint_name
                        multiline_value = [prompt[:-1].strip()]
                    else:
                        data.endpoints[endpoint_name] = prompt
                        multiline_key = None
                        multiline_value = []
                elif multiline_key:
                    if stripped.endswith('\\'):
                        multiline_value.append(stripped[:-1].strip())
                    else:
                        multiline_value.append(stripped)
                        data.endpoints[multiline_key] = ' '.join(multiline_value)
                        multiline_key = None
                        multiline_value = []
            
            elif current_section in data.keys:
                if stripped and not stripped.startswith('#'):
                    data.keys[current_section].append(stripped)
        
        # Flush any remaining multiline
        if multiline_key and current_section == 'endpoints':
            data.endpoints[multiline_key] = ' '.join(multiline_value)
        
    except Exception as e:
        print(f"[SettingsWindow] Error parsing config: {e}")
    
    return data


def _parse_value(value_str: str) -> Any:
    """Parse a configuration value from string to appropriate type."""
    value_str = value_str.strip()
    if value_str.lower() in ['none', 'null', '']:
        return None
    if value_str.lower() in ['true', 'yes', 'on', '1']:
        return True
    if value_str.lower() in ['false', 'no', 'off', '0']:
        return False
    try:
        if '.' not in value_str:
            return int(value_str)
        return float(value_str)
    except ValueError:
        pass
    # Remove quotes
    if (value_str.startswith('"') and value_str.endswith('"')) or \
       (value_str.startswith("'") and value_str.endswith("'")):
        return value_str[1:-1]
    return value_str


def _value_to_str(value: Any) -> str:
    """Convert a value to config file string format."""
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def save_config_full(data: ConfigData, filepath: str = "config.ini") -> bool:
    """
    Save full config preserving comments and structure.
    Creates a backup before saving.
    
    Returns:
        True if save was successful
    """
    try:
        # Create backup
        if Path(filepath).exists():
            backup_path = filepath + ".bak"
            shutil.copy2(filepath, backup_path)
        
        # Rebuild the file
        lines = []
        current_section = None
        written_keys = set()
        written_endpoints = set()
        written_api_keys = {"custom": set(), "openrouter": set(), "google": set()}
        
        for line in data.raw_lines:
            raw_line = line.rstrip('\n\r')
            stripped = raw_line.strip()
            
            # Section header
            if stripped.startswith('[') and stripped.endswith(']'):
                current_section = stripped[1:-1].lower()
                lines.append(raw_line + '\n')
                continue
            
            # Comment or empty - preserve as-is
            if not stripped or stripped.startswith('#'):
                lines.append(raw_line + '\n')
                continue
            
            # Handle based on section
            if current_section == 'config' and '=' in stripped:
                key = stripped.split('=', 1)[0].strip().lower()
                if key in data.config:
                    value = _value_to_str(data.config[key])
                    lines.append(f"{key} = {value}\n")
                    written_keys.add(key)
                else:
                    lines.append(raw_line + '\n')
            
            elif current_section == 'endpoints' and '=' in stripped:
                # Skip multiline continuations (handled with main key)
                if not stripped.startswith(' ') and not stripped.startswith('\t'):
                    endpoint_name = stripped.split('=', 1)[0].strip().lower()
                    if endpoint_name in data.endpoints and endpoint_name not in written_endpoints:
                        prompt = data.endpoints[endpoint_name]
                        lines.append(f"{endpoint_name} = {prompt}\n")
                        written_endpoints.add(endpoint_name)
                    elif endpoint_name not in written_endpoints:
                        lines.append(raw_line + '\n')
                # Skip continuation lines (they were merged)
            
            elif current_section in data.keys:
                # Rewrite API keys section
                if stripped and not stripped.startswith('#'):
                    # Skip old keys, we'll write new ones at the end
                    continue
                lines.append(raw_line + '\n')
            
            else:
                lines.append(raw_line + '\n')
        
        # Add new config keys not in original file
        config_section_end = _find_section_end(lines, 'config')
        new_config_lines = []
        for key, value in data.config.items():
            if key not in written_keys:
                new_config_lines.append(f"{key} = {_value_to_str(value)}\n")
        if new_config_lines and config_section_end > 0:
            lines = lines[:config_section_end] + new_config_lines + lines[config_section_end:]
        
        # Add API keys at end of their sections
        for section in ['custom', 'openrouter', 'google']:
            section_end = _find_section_end(lines, section)
            if section_end > 0:
                key_lines = [key + '\n' for key in data.keys[section]]
                lines = lines[:section_end] + key_lines + lines[section_end:]
        
        # Write file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        return True
    
    except Exception as e:
        print(f"[SettingsWindow] Error saving config: {e}")
        return False


def _find_section_end(lines: List[str], section: str) -> int:
    """Find the line index where a section ends (next section or EOF)."""
    in_section = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            if in_section:
                return i
            if stripped[1:-1].lower() == section:
                in_section = True
    return len(lines) if in_section else -1


# =============================================================================
# Custom Widgets
# =============================================================================

class ToggleSwitch(tk.Canvas):
    """Custom toggle switch widget."""
    
    def __init__(self, parent, variable: tk.BooleanVar, colors: ThemeColors, 
                 command: Optional[Callable] = None, **kwargs):
        self.width = kwargs.pop('width', 50)
        self.height = kwargs.pop('height', 24)
        super().__init__(parent, width=self.width, height=self.height, 
                        highlightthickness=0, **kwargs)
        
        self.variable = variable
        self.colors = colors
        self.command = command
        
        self.configure(bg=colors.bg)
        self.bind('<Button-1>', self._toggle)
        self.variable.trace_add('write', lambda *args: self._draw())
        self._draw()
    
    def _draw(self):
        """Draw the toggle switch."""
        self.delete('all')
        
        is_on = self.variable.get()
        
        # Track
        track_color = self.colors.accent_green if is_on else self.colors.surface1
        self.create_oval(2, 2, self.height - 2, self.height - 2, 
                        fill=track_color, outline=track_color)
        self.create_oval(self.width - self.height + 2, 2, 
                        self.width - 2, self.height - 2,
                        fill=track_color, outline=track_color)
        self.create_rectangle(self.height // 2, 2, 
                             self.width - self.height // 2, self.height - 2,
                             fill=track_color, outline=track_color)
        
        # Knob
        knob_x = self.width - self.height // 2 - 4 if is_on else self.height // 2 + 4
        self.create_oval(knob_x - 8, 4, knob_x + 8, self.height - 4,
                        fill='#ffffff', outline='#ffffff')
    
    def _toggle(self, event=None):
        """Toggle the switch."""
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()


# Note: HotkeyEntry removed - hotkeys are now typed manually as text
# e.g. "ctrl+space", "escape", "alt+tab"


# =============================================================================
# Settings Window
# =============================================================================

class SettingsWindow:
    """
    Standalone settings window that creates its own Tk root.
    Used when launching from non-GUI contexts.
    """
    
    def __init__(self):
        self.window_id = get_next_window_id()
        self.window_tag = f"settings_{self.window_id}"
        
        self.colors = get_colors()
        self.root: Optional[tk.Tk] = None
        self._destroyed = False
        
        # Config data
        self.config_data: Optional[ConfigData] = None
        self.original_config: Dict[str, Any] = {}
        
        # Widget references for saving
        self.widgets: Dict[str, Any] = {}
        self.vars: Dict[str, tk.Variable] = {}
        
        # Theme preview
        self.preview_frame: Optional[tk.Frame] = None
    
    def show(self, initial_tab: str = None):
        """
        Create and show the settings window.
        
        Args:
            initial_tab: Name of the tab to select initially (e.g. "API Keys")
        """
        # Load current config
        self.config_data = parse_config_full()
        self.original_config = dict(self.config_data.config)
        
        # Load from web_server if available (in-memory values)
        try:
            from .. import web_server
            for key, value in web_server.CONFIG.items():
                self.config_data.config[key] = value
        except (ImportError, AttributeError):
            pass
        
        self.root = tk.Tk()
        self.root.title("AI Bridge Settings")
        self.root.geometry("950x700")
        self.root.configure(bg=self.colors.bg)
        self.root.minsize(900, 600)
        
        # Position window
        offset = (self.window_id % 3) * 30
        self.root.geometry(f"+{100 + offset}+{100 + offset}")
        
        # Configure grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        
        # Title bar
        self._create_title_bar()
        
        # Notebook (tabs)
        self._create_notebook()
        
        # Select initial tab if specified
        if initial_tab:
            try:
                for tab_id in self.notebook.tabs():
                    if self.notebook.tab(tab_id, "text") == initial_tab:
                        self.notebook.select(tab_id)
                        break
            except Exception as e:
                print(f"[SettingsWindow] Failed to select initial tab '{initial_tab}': {e}")
        
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
            text="⚙️ Settings",
            font=("Segoe UI", 16, "bold"),
            bg=self.colors.bg,
            fg=self.colors.fg
        ).pack(side=tk.LEFT)
        
        tk.Label(
            title_frame,
            text="Edit config.ini",
            font=("Segoe UI", 10),
            bg=self.colors.bg,
            fg=self.colors.blockquote
        ).pack(side=tk.LEFT, padx=(15, 0))
    
    def _create_notebook(self):
        """Create the tabbed notebook."""
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
        self._create_general_tab()
        self._create_provider_tab()
        self._create_streaming_tab()
        self._create_textedit_tab()
        self._create_keys_tab()
        self._create_endpoints_tab()
        self._create_theme_tab()
    
    def _create_general_tab(self):
        """Create the General settings tab."""
        frame = tk.Frame(self.notebook, bg=self.colors.bg)
        self.notebook.add(frame, text="General")
        
        # Inner frame with padding
        inner = tk.Frame(frame, bg=self.colors.bg)
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        inner.columnconfigure(2, weight=1)  # Description column expands
        
        row = 0
        
        # Server settings
        tk.Label(inner, text="Server Settings", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))
        row += 1
        
        # Host
        row = self._add_entry_field(inner, row, "host", "Host:",
                                   self.config_data.config.get("host", "127.0.0.1"),
                                   hint="⚠️ Restart required. IP address to bind.")
        
        # Port
        row = self._add_entry_field(inner, row, "port", "Port:",
                                   str(self.config_data.config.get("port", 5000)),
                                   validate="port",
                                   hint="⚠️ Restart required. Port for Flask server (1-65535)")
        
        # Behavior settings
        tk.Label(inner, text="Behavior", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=3, sticky=tk.W, pady=(20, 10))
        row += 1
        
        # Show AI response in chat window
        row = self._add_toggle_field(inner, row, "show_ai_response_in_chat_window",
                                    "Show AI response in chat window",
                                    self.config_data.config.get("show_ai_response_in_chat_window", "no") == "yes",
                                    hint="For endpoint requests only. TextEditTool actions/modifiers override this.")
        
        # Limits
        tk.Label(inner, text="Limits", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=3, sticky=tk.W, pady=(20, 10))
        row += 1
        
        # Max sessions
        row = self._add_spinbox_field(inner, row, "max_sessions", "Max sessions:",
                                     self.config_data.config.get("max_sessions", 50),
                                     1, 1000,
                                     hint="Maximum number of chat sessions to keep")
        
        # Max retries
        row = self._add_spinbox_field(inner, row, "max_retries", "Max retries:",
                                     self.config_data.config.get("max_retries", 3),
                                     0, 10,
                                     hint="Retries before giving up on API calls")
        
        # Retry delay
        row = self._add_spinbox_field(inner, row, "retry_delay", "Retry delay (s):",
                                     self.config_data.config.get("retry_delay", 5),
                                     1, 60,
                                     hint="Seconds to wait between retries")
        
        # Request timeout
        row = self._add_spinbox_field(inner, row, "request_timeout", "Request timeout (s):",
                                     self.config_data.config.get("request_timeout", 120),
                                     10, 600,
                                     hint="Timeout for API requests")
    
    def _create_provider_tab(self):
        """Create the Provider settings tab."""
        frame = tk.Frame(self.notebook, bg=self.colors.bg)
        self.notebook.add(frame, text="Provider")
        
        inner = tk.Frame(frame, bg=self.colors.bg)
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        row = 0
        
        # Default provider
        tk.Label(inner, text="Default Provider", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        row += 1
        
        current_provider = self.config_data.config.get("default_provider", "google")
        self.vars["default_provider"] = tk.StringVar(master=self.root, value=current_provider)
        
        tk.Label(inner, text="Provider:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        
        provider_combo = ttk.Combobox(inner, textvariable=self.vars["default_provider"],
                                     values=["custom", "openrouter", "google"],
                                     state="readonly", width=25)
        provider_combo.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        self.widgets["default_provider"] = provider_combo
        row += 1
        
        # Custom provider settings
        tk.Label(inner, text="Custom Provider", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=2, sticky=tk.W, pady=(20, 10))
        row += 1
        
        row = self._add_entry_field(inner, row, "custom_url", "URL:",
                                   self.config_data.config.get("custom_url", "") or "",
                                   width=50)
        
        row = self._add_entry_field(inner, row, "custom_model", "Model:",
                                   self.config_data.config.get("custom_model", "") or "",
                                   width=40)
        
        # OpenRouter settings
        tk.Label(inner, text="OpenRouter", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=2, sticky=tk.W, pady=(20, 10))
        row += 1
        
        row = self._add_entry_field(inner, row, "openrouter_model", "Model:",
                                   self.config_data.config.get("openrouter_model", ""),
                                   width=40)
        
        # Google settings
        tk.Label(inner, text="Google Gemini", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=2, sticky=tk.W, pady=(20, 10))
        row += 1
        
        row = self._add_entry_field(inner, row, "google_model", "Model:",
                                   self.config_data.config.get("google_model", ""),
                                   width=40)
    
    def _create_streaming_tab(self):
        """Create the Streaming/Thinking settings tab."""
        frame = tk.Frame(self.notebook, bg=self.colors.bg)
        self.notebook.add(frame, text="Streaming")
        
        inner = tk.Frame(frame, bg=self.colors.bg)
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        row = 0
        
        # Streaming
        tk.Label(inner, text="Streaming", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        row += 1
        
        row = self._add_toggle_field(inner, row, "streaming_enabled",
                                    "Enable streaming responses",
                                    self.config_data.config.get("streaming_enabled", True))
        
        # Thinking
        tk.Label(inner, text="Thinking / Reasoning", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=2, sticky=tk.W, pady=(20, 10))
        row += 1
        
        row = self._add_toggle_field(inner, row, "thinking_enabled",
                                    "Enable thinking mode",
                                    self.config_data.config.get("thinking_enabled", False))
        
        # Thinking output
        tk.Label(inner, text="Thinking output:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        
        self.vars["thinking_output"] = tk.StringVar(
            master=self.root, value=self.config_data.config.get("thinking_output", "reasoning_content"))
        thinking_combo = ttk.Combobox(inner, textvariable=self.vars["thinking_output"],
                                     values=["filter", "raw", "reasoning_content"],
                                     state="readonly", width=20)
        thinking_combo.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        self.widgets["thinking_output"] = thinking_combo
        row += 1
        
        # Thinking config
        tk.Label(inner, text="Thinking Configuration", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=2, sticky=tk.W, pady=(20, 10))
        row += 1
        
        # Reasoning effort (OpenAI)
        tk.Label(inner, text="Reasoning effort (OpenAI):", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        
        self.vars["reasoning_effort"] = tk.StringVar(
            master=self.root, value=self.config_data.config.get("reasoning_effort", "high"))
        effort_combo = ttk.Combobox(inner, textvariable=self.vars["reasoning_effort"],
                                   values=["low", "medium", "high"],
                                   state="readonly", width=15)
        effort_combo.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        self.widgets["reasoning_effort"] = effort_combo
        row += 1
        
        # Thinking budget (Gemini 2.5)
        row = self._add_spinbox_field(inner, row, "thinking_budget", 
                                     "Thinking budget (Gemini 2.5):",
                                     self.config_data.config.get("thinking_budget", -1),
                                     -1, 100000)
        
        # Thinking level (Gemini 3.x)
        tk.Label(inner, text="Thinking level (Gemini 3.x):", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        
        self.vars["thinking_level"] = tk.StringVar(
            master=self.root, value=self.config_data.config.get("thinking_level", "high"))
        level_combo = ttk.Combobox(inner, textvariable=self.vars["thinking_level"],
                                  values=["low", "high"],
                                  state="readonly", width=15)
        level_combo.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        self.widgets["thinking_level"] = level_combo
    
    def _create_textedit_tab(self):
        """Create the TextEditTool settings tab."""
        frame = tk.Frame(self.notebook, bg=self.colors.bg)
        self.notebook.add(frame, text="TextEditTool")
        
        inner = tk.Frame(frame, bg=self.colors.bg)
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        row = 0
        
        # Enable/Disable
        tk.Label(inner, text="TextEditTool", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        row += 1
        
        row = self._add_toggle_field(inner, row, "text_edit_tool_enabled",
                                    "Enable TextEditTool",
                                    self.config_data.config.get("text_edit_tool_enabled", True),
                                    hint="⚠️ Restart required")
        
        # Hotkeys
        tk.Label(inner, text="Hotkeys", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=3, sticky=tk.W, pady=(20, 10))
        row += 1
        
        row = self._add_hotkey_field(inner, row, "text_edit_tool_hotkey",
                                    "Activation hotkey:",
                                    self.config_data.config.get("text_edit_tool_hotkey", "ctrl+space"),
                                    hint="⚠️ Restart required")
        
        row = self._add_hotkey_field(inner, row, "text_edit_tool_abort_hotkey",
                                    "Abort hotkey:",
                                    self.config_data.config.get("text_edit_tool_abort_hotkey", "escape"),
                                    hint="⚠️ Restart required")
        
        # Typing settings
        tk.Label(inner, text="Typing Settings", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=3, sticky=tk.W, pady=(20, 10))
        row += 1
        
        row = self._add_spinbox_field(inner, row, "streaming_typing_delay",
                                     "Typing delay (ms):",
                                     self.config_data.config.get("streaming_typing_delay", 5),
                                     1, 100,
                                     hint="Delay per character when streaming typing (replace mode)")
        
        row = self._add_toggle_field(inner, row, "streaming_typing_uncapped",
                                    "Uncapped typing speed",
                                    self.config_data.config.get("streaming_typing_uncapped", False),
                                    hint="⚠️ No delay between chars. May overwhelm some apps.")
    
    def _create_keys_tab(self):
        """Create the API Keys settings tab."""
        frame = tk.Frame(self.notebook, bg=self.colors.bg)
        self.notebook.add(frame, text="API Keys")
        
        inner = tk.Frame(frame, bg=self.colors.bg)
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        # Create sub-notebook for each provider
        keys_notebook = ttk.Notebook(inner)
        keys_notebook.pack(fill=tk.BOTH, expand=True)
        
        for provider in ["custom", "openrouter", "google"]:
            self._create_keys_section(keys_notebook, provider)
    
    def _create_keys_section(self, parent: ttk.Notebook, provider: str):
        """Create a key management section for a provider."""
        frame = tk.Frame(parent, bg=self.colors.bg)
        parent.add(frame, text=provider.capitalize())
        
        # Instructions
        tk.Label(
            frame,
            text=f"Manage {provider} API keys (one per line, keys are masked for security)",
            font=("Segoe UI", 9),
            bg=self.colors.bg,
            fg=self.colors.blockquote
        ).pack(anchor=tk.W, pady=(10, 5), padx=10)
        
        # Key list frame
        list_frame = tk.Frame(frame, bg=self.colors.bg)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Listbox
        listbox = tk.Listbox(
            list_frame,
            font=("Consolas", 10),
            bg=self.colors.input_bg,
            fg=self.colors.fg,
            selectbackground=self.colors.accent,
            selectforeground="#ffffff",
            relief=tk.FLAT,
            highlightbackground=self.colors.border,
            highlightthickness=1,
            height=8
        )
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.configure(yscrollcommand=scrollbar.set)
        
        # Populate with masked keys
        for key in self.config_data.keys.get(provider, []):
            masked = self._mask_key(key)
            listbox.insert(tk.END, masked)
        
        self.widgets[f"keys_{provider}_listbox"] = listbox
        self.widgets[f"keys_{provider}_data"] = list(self.config_data.keys.get(provider, []))
        
        # Button frame
        btn_frame = tk.Frame(frame, bg=self.colors.bg)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Add key entry
        entry_var = tk.StringVar(master=frame)
        key_entry = tk.Entry(
            btn_frame,
            textvariable=entry_var,
            font=("Consolas", 10),
            bg=self.colors.input_bg,
            fg=self.colors.fg,
            insertbackground=self.colors.fg,
            relief=tk.FLAT,
            highlightbackground=self.colors.border,
            highlightthickness=1,
            width=40
        )
        key_entry.pack(side=tk.LEFT, padx=(0, 10), ipady=5)
        key_entry.insert(0, "Paste new API key here...")
        key_entry.configure(fg=self.colors.blockquote)
        
        def on_focus_in(e):
            if key_entry.get() == "Paste new API key here...":
                key_entry.delete(0, tk.END)
                key_entry.configure(fg=self.colors.fg)
        
        def on_focus_out(e):
            if not key_entry.get():
                key_entry.insert(0, "Paste new API key here...")
                key_entry.configure(fg=self.colors.blockquote)
        
        key_entry.bind('<FocusIn>', on_focus_in)
        key_entry.bind('<FocusOut>', on_focus_out)
        
        def add_key():
            key = entry_var.get().strip()
            if key and key != "Paste new API key here...":
                self.widgets[f"keys_{provider}_data"].append(key)
                listbox.insert(tk.END, self._mask_key(key))
                entry_var.set("")
                key_entry.insert(0, "Paste new API key here...")
                key_entry.configure(fg=self.colors.blockquote)
        
        def remove_key():
            selection = listbox.curselection()
            if selection:
                idx = selection[0]
                listbox.delete(idx)
                del self.widgets[f"keys_{provider}_data"][idx]
        
        tk.Button(
            btn_frame,
            text="Add",
            font=("Segoe UI", 10),
            bg=self.colors.accent_green,
            fg="#ffffff",
            activebackground="#45a049",
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=add_key
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_frame,
            text="Remove",
            font=("Segoe UI", 10),
            bg=self.colors.accent_red,
            fg="#ffffff",
            activebackground="#c0392b",
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=remove_key
        ).pack(side=tk.LEFT, padx=2)
    
    def _mask_key(self, key: str) -> str:
        """Mask an API key for display."""
        if len(key) <= 8:
            return "*" * len(key)
        return key[:4] + "..." + key[-4:]
    
    def _create_endpoints_tab(self):
        """Create the Endpoints settings tab."""
        frame = tk.Frame(self.notebook, bg=self.colors.bg)
        self.notebook.add(frame, text="Endpoints")
        
        inner = tk.Frame(frame, bg=self.colors.bg)
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        inner.columnconfigure(0, weight=1)
        inner.columnconfigure(1, weight=2)
        inner.rowconfigure(1, weight=1)
        
        # Left: endpoint list
        tk.Label(inner, text="Endpoints", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=0, column=0, sticky=tk.W, pady=(0, 10))
        
        list_frame = tk.Frame(inner, bg=self.colors.bg)
        list_frame.grid(row=1, column=0, sticky=tk.NSEW, padx=(0, 10))
        
        self.endpoint_listbox = tk.Listbox(
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
        self.endpoint_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, 
                                 command=self.endpoint_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.endpoint_listbox.configure(yscrollcommand=scrollbar.set)
        
        # Populate endpoints
        for name in sorted(self.config_data.endpoints.keys()):
            self.endpoint_listbox.insert(tk.END, name)
        
        self.endpoint_listbox.bind('<<ListboxSelect>>', self._on_endpoint_select)
        
        # Right: prompt editor
        tk.Label(inner, text="Prompt", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=0, column=1, sticky=tk.W, pady=(0, 10))
        
        self.endpoint_text = tk.Text(
            inner,
            font=("Segoe UI", 10),
            bg=self.colors.input_bg,
            fg=self.colors.fg,
            insertbackground=self.colors.fg,
            relief=tk.FLAT,
            highlightbackground=self.colors.border,
            highlightthickness=1,
            wrap=tk.WORD,
            height=10
        )
        self.endpoint_text.grid(row=1, column=1, sticky=tk.NSEW)
        
        # Button row
        btn_frame = tk.Frame(inner, bg=self.colors.bg)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=(10, 0))
        
        tk.Button(
            btn_frame,
            text="Save Prompt",
            font=("Segoe UI", 10),
            bg=self.colors.accent_green,
            fg="#ffffff",
            activebackground="#45a049",
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._save_endpoint
        ).pack(side=tk.LEFT, padx=2)
        
        self.endpoint_status = tk.Label(
            btn_frame,
            text="",
            font=("Segoe UI", 9),
            bg=self.colors.bg,
            fg=self.colors.accent_green
        )
        self.endpoint_status.pack(side=tk.LEFT, padx=15)
    
    def _on_endpoint_select(self, event):
        """Handle endpoint selection."""
        selection = self.endpoint_listbox.curselection()
        if selection:
            name = self.endpoint_listbox.get(selection[0])
            prompt = self.config_data.endpoints.get(name, "")
            self.endpoint_text.delete("1.0", tk.END)
            self.endpoint_text.insert("1.0", prompt)
    
    def _save_endpoint(self):
        """Save the currently edited endpoint."""
        selection = self.endpoint_listbox.curselection()
        if selection:
            name = self.endpoint_listbox.get(selection[0])
            prompt = self.endpoint_text.get("1.0", tk.END).strip()
            self.config_data.endpoints[name] = prompt
            self.endpoint_status.configure(text=f"✅ Saved '{name}'", fg=self.colors.accent_green)
    
    def _create_theme_tab(self):
        """Create the Theme settings tab."""
        frame = tk.Frame(self.notebook, bg=self.colors.bg)
        self.notebook.add(frame, text="Theme")
        
        inner = tk.Frame(frame, bg=self.colors.bg)
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        row = 0
        
        # Theme selection
        tk.Label(inner, text="UI Theme", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        row += 1
        
        # Theme dropdown
        tk.Label(inner, text="Theme:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        
        current_theme = self.config_data.config.get("ui_theme", "catppuccin")
        self.vars["ui_theme"] = tk.StringVar(master=self.root, value=current_theme)
        
        theme_combo = ttk.Combobox(inner, textvariable=self.vars["ui_theme"],
                                  values=list_themes(),
                                  state="readonly", width=20)
        theme_combo.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        theme_combo.bind('<<ComboboxSelected>>', self._update_theme_preview)
        self.widgets["ui_theme"] = theme_combo
        row += 1
        
        # Mode dropdown
        tk.Label(inner, text="Mode:", font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        
        current_mode = self.config_data.config.get("ui_theme_mode", "auto")
        self.vars["ui_theme_mode"] = tk.StringVar(master=self.root, value=current_mode)
        
        mode_combo = ttk.Combobox(inner, textvariable=self.vars["ui_theme_mode"],
                                 values=["auto", "dark", "light"],
                                 state="readonly", width=15)
        mode_combo.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        mode_combo.bind('<<ComboboxSelected>>', self._update_theme_preview)
        self.widgets["ui_theme_mode"] = mode_combo
        row += 1
        
        # Preview section
        tk.Label(inner, text="Preview", font=("Segoe UI", 11, "bold"),
                bg=self.colors.bg, fg=self.colors.accent).grid(
                row=row, column=0, columnspan=2, sticky=tk.W, pady=(20, 10))
        row += 1
        
        # Preview frame
        self.preview_frame = tk.Frame(inner, bg=self.colors.surface0,
                                     highlightbackground=self.colors.border,
                                     highlightthickness=1)
        self.preview_frame.grid(row=row, column=0, columnspan=2, sticky=tk.NSEW, pady=5)
        
        self._update_theme_preview()
    
    def _update_theme_preview(self, event=None):
        """Update the theme preview."""
        if not self.preview_frame:
            return
        
        # Clear preview
        for widget in self.preview_frame.winfo_children():
            widget.destroy()
        
        # Get preview colors
        theme_name = self.vars["ui_theme"].get()
        mode = self.vars["ui_theme_mode"].get()
        
        if mode == "auto":
            is_dark = ThemeRegistry.is_dark_mode()
        else:
            is_dark = mode == "dark"
        
        preview_colors = ThemeRegistry.get_theme(theme_name, "dark" if is_dark else "light")
        
        # Update preview frame background
        self.preview_frame.configure(bg=preview_colors.bg)
        
        # Add sample elements
        inner = tk.Frame(self.preview_frame, bg=preview_colors.bg)
        inner.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Title
        tk.Label(
            inner,
            text=f"Theme: {theme_name.title()} ({'Dark' if is_dark else 'Light'})",
            font=("Segoe UI", 12, "bold"),
            bg=preview_colors.bg,
            fg=preview_colors.fg
        ).pack(anchor=tk.W)
        
        # Sample text
        tk.Label(
            inner,
            text="This is how text will look in this theme.",
            font=("Segoe UI", 10),
            bg=preview_colors.bg,
            fg=preview_colors.fg
        ).pack(anchor=tk.W, pady=(5, 0))
        
        # Sample muted text
        tk.Label(
            inner,
            text="Muted/secondary text appears like this.",
            font=("Segoe UI", 9),
            bg=preview_colors.bg,
            fg=preview_colors.blockquote
        ).pack(anchor=tk.W)
        
        # Sample buttons row
        btn_row = tk.Frame(inner, bg=preview_colors.bg)
        btn_row.pack(anchor=tk.W, pady=(10, 0))
        
        tk.Label(
            btn_row,
            text="Primary",
            font=("Segoe UI", 9),
            bg=preview_colors.accent,
            fg="#ffffff",
            padx=10,
            pady=3
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Label(
            btn_row,
            text="Success",
            font=("Segoe UI", 9),
            bg=preview_colors.accent_green,
            fg="#ffffff",
            padx=10,
            pady=3
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Label(
            btn_row,
            text="Warning",
            font=("Segoe UI", 9),
            bg=preview_colors.accent_yellow,
            fg="#000000",
            padx=10,
            pady=3
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Label(
            btn_row,
            text="Danger",
            font=("Segoe UI", 9),
            bg=preview_colors.accent_red,
            fg="#ffffff",
            padx=10,
            pady=3
        ).pack(side=tk.LEFT, padx=2)
        
        # Sample input
        sample_entry = tk.Entry(
            inner,
            font=("Segoe UI", 10),
            bg=preview_colors.input_bg,
            fg=preview_colors.fg,
            insertbackground=preview_colors.fg,
            relief=tk.FLAT,
            highlightbackground=preview_colors.border,
            highlightthickness=1
        )
        sample_entry.insert(0, "Sample input field")
        sample_entry.pack(anchor=tk.W, pady=(10, 0), ipady=5)
    
    # Helper methods for creating form fields
    
    def _add_entry_field(self, parent, row: int, key: str, label: str,
                        value: str, width: int = 25, validate: str = None,
                        hint: str = None) -> int:
        """Add an entry field to the form with optional hint."""
        tk.Label(parent, text=label, font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        
        self.vars[key] = tk.StringVar(master=self.root, value=value)
        entry = tk.Entry(
            parent,
            textvariable=self.vars[key],
            font=("Segoe UI", 10),
            bg=self.colors.input_bg,
            fg=self.colors.fg,
            insertbackground=self.colors.fg,
            relief=tk.FLAT,
            highlightbackground=self.colors.border,
            highlightthickness=1,
            width=width
        )
        entry.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0), ipady=4)
        self.widgets[key] = entry
        
        # Add hint if provided
        if hint:
            tk.Label(parent, text=hint, font=("Segoe UI", 9),
                    bg=self.colors.bg, fg=self.colors.blockquote).grid(
                    row=row, column=2, sticky=tk.W, padx=(15, 0))
        
        return row + 1
    
    def _add_toggle_field(self, parent, row: int, key: str, label: str,
                         value: bool, hint: str = None) -> int:
        """Add a toggle switch field to the form with optional hint."""
        tk.Label(parent, text=label, font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        
        self.vars[key] = tk.BooleanVar(master=self.root, value=value)
        toggle = ToggleSwitch(parent, self.vars[key], self.colors)
        toggle.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        self.widgets[key] = toggle
        
        # Add hint if provided
        if hint:
            tk.Label(parent, text=hint, font=("Segoe UI", 9),
                    bg=self.colors.bg, fg=self.colors.blockquote).grid(
                    row=row, column=2, sticky=tk.W, padx=(15, 0))
        
        return row + 1
    
    def _add_spinbox_field(self, parent, row: int, key: str, label: str,
                          value: int, min_val: int, max_val: int,
                          hint: str = None) -> int:
        """Add a spinbox field to the form with optional hint."""
        tk.Label(parent, text=label, font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        
        self.vars[key] = tk.IntVar(master=self.root, value=value)
        spinbox = ttk.Spinbox(
            parent,
            textvariable=self.vars[key],
            from_=min_val,
            to=max_val,
            width=10
        )
        spinbox.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        self.widgets[key] = spinbox
        
        # Add hint if provided
        if hint:
            tk.Label(parent, text=hint, font=("Segoe UI", 9),
                    bg=self.colors.bg, fg=self.colors.blockquote).grid(
                    row=row, column=2, sticky=tk.W, padx=(15, 0))
        
        return row + 1
    
    def _add_hotkey_field(self, parent, row: int, key: str, label: str,
                         value: str, hint: str = None) -> int:
        """Add a hotkey text entry field to the form with optional hint.
        
        Hotkeys are typed manually, e.g. 'ctrl+space', 'escape', 'alt+tab'.
        """
        tk.Label(parent, text=label, font=("Segoe UI", 10),
                bg=self.colors.bg, fg=self.colors.fg).grid(
                row=row, column=0, sticky=tk.W, pady=5)
        
        self.vars[key] = tk.StringVar(master=self.root, value=value)
        entry = tk.Entry(
            parent,
            textvariable=self.vars[key],
            font=("Segoe UI", 10),
            bg=self.colors.input_bg,
            fg=self.colors.fg,
            insertbackground=self.colors.fg,
            relief=tk.FLAT,
            highlightbackground=self.colors.border,
            highlightthickness=1,
            width=20
        )
        entry.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0), ipady=4)
        self.widgets[key] = entry
        
        # Add hint if provided
        if hint:
            tk.Label(parent, text=hint, font=("Segoe UI", 9),
                    bg=self.colors.bg, fg=self.colors.blockquote).grid(
                    row=row, column=2, sticky=tk.W, padx=(15, 0))
        
        return row + 1
    
    def _create_button_bar(self):
        """Create the bottom button bar."""
        btn_frame = tk.Frame(self.root, bg=self.colors.bg)
        btn_frame.grid(row=2, column=0, sticky=tk.EW, padx=20, pady=(10, 20))
        
        tk.Button(
            btn_frame,
            text="💾 Save",
            font=("Segoe UI", 11),
            bg=self.colors.accent_green,
            fg="#ffffff",
            activebackground="#45a049",
            relief=tk.FLAT,
            padx=20,
            pady=8,
            command=self._save
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
    
    def _validate(self) -> tuple:
        """
        Validate all fields.
        
        Returns:
            (is_valid, error_message)
        """
        # Validate port
        try:
            port_var = self.vars.get("port")
            if port_var:
                port = int(port_var.get())
                if port < 1 or port > 65535:
                    return False, "Port must be between 1 and 65535"
        except ValueError:
            return False, "Port must be a number"
        
        return True, ""
    
    def _save(self):
        """Save all settings."""
        # Validate
        is_valid, error = self._validate()
        if not is_valid:
            messagebox.showerror("Validation Error", error)
            return
        
        # Collect values from widgets
        for key, var in self.vars.items():
            value = var.get()
            
            # Handle special cases
            if key == "show_ai_response_in_chat_window":
                value = "yes" if value else "no"
            elif key == "port":
                value = int(value)
            
            self.config_data.config[key] = value
        
        # Collect API keys
        for provider in ["custom", "openrouter", "google"]:
            data_key = f"keys_{provider}_data"
            if data_key in self.widgets:
                self.config_data.keys[provider] = self.widgets[data_key]
        
        # Save to file
        if save_config_full(self.config_data):
            # Update in-memory config
            try:
                from .. import web_server
                for key, value in self.config_data.config.items():
                    web_server.CONFIG[key] = value
                
                # Hot-reload API keys without restart
                for provider in ["custom", "openrouter", "google"]:
                    if provider in web_server.KEY_MANAGERS:
                        new_keys = self.config_data.keys.get(provider, [])
                        web_server.KEY_MANAGERS[provider].keys = [k for k in new_keys if k]
                        web_server.KEY_MANAGERS[provider].current_index = 0
                        web_server.KEY_MANAGERS[provider].exhausted_keys.clear()
                        print(f"[Settings] Reloaded {len(new_keys)} {provider} API key(s)")
                
                # Hot-reload endpoints without restart
                for endpoint_name, prompt in self.config_data.endpoints.items():
                    web_server.ENDPOINTS[endpoint_name] = prompt
                print(f"[Settings] Reloaded {len(self.config_data.endpoints)} endpoint(s)")
                
            except (ImportError, AttributeError) as e:
                print(f"[Settings] Note: Could not update in-memory config: {e}")
            
            self.status_label.configure(text="✅ Settings saved!", fg=self.colors.accent_green)
            
            # Close after brief delay
            self.root.after(1000, self._close)
        else:
            self.status_label.configure(text="❌ Failed to save", fg=self.colors.accent_red)
    
    def _close(self):
        """Close the settings window."""
        self._destroyed = True
        unregister_window(self.window_tag)
        try:
            if self.root:
                self.root.destroy()
        except tk.TclError:
            pass
        self.root = None


class AttachedSettingsWindow:
    """
    Settings window as Toplevel attached to GUICoordinator's root.
    Used for centralized GUI threading.
    """
    
    def __init__(self, parent_root: tk.Tk):
        self.parent_root = parent_root
        self.window_id = get_next_window_id()
        self.window_tag = f"attached_settings_{self.window_id}"
        
        self.colors = get_colors()
        self._destroyed = False
        
        # Create a standalone window since Settings is complex
        # and needs its own event handling
        def run_settings():
            settings = SettingsWindow()
            settings.show()
        
        # Run in thread to not block coordinator
        threading.Thread(target=run_settings, daemon=True).start()


def create_attached_settings_window(parent_root: tk.Tk):
    """Create a settings window (called on GUI thread)."""
    AttachedSettingsWindow(parent_root)


def show_settings_window():
    """Show settings window - can be called from any thread."""
    def run():
        settings = SettingsWindow()
        settings.show()
    
    threading.Thread(target=run, daemon=True).start()