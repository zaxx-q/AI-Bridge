#!/usr/bin/env python3
"""
Settings Window for AI Bridge

Provides a GUI for editing config.ini without opening the file directly.
Features:
- Tabbed interface for different config sections
- Theme selector with live preview
- Validation for fields like ports, hotkeys
- Save/Cancel with backup creation

CustomTkinter Migration: Uses CTk widgets for modern UI.
"""

import os
import sys
import re
import time
import shutil
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Dict, Optional, List, Callable, Any
from pathlib import Path

import threading

# Import CustomTkinter with fallback
try:
    import customtkinter as ctk
    _CTK_AVAILABLE = True
    HAVE_CTK = True
except ImportError:
    _CTK_AVAILABLE = False
    HAVE_CTK = False
    ctk = None


def _can_use_ctk() -> bool:
    """
    Check if CustomTkinter can be safely used.
    """
    return _CTK_AVAILABLE

from .themes import (
    ThemeRegistry, ThemeColors, get_colors, list_themes, sync_ctk_appearance,
    get_ctk_button_colors, get_ctk_frame_colors, get_ctk_entry_colors,
    get_ctk_textbox_colors, get_ctk_combobox_colors, get_ctk_label_colors,
    get_ctk_font
)
from .core import get_next_window_id, register_window, unregister_window
from .custom_widgets import ScrollableButtonList, upgrade_tabview_with_icons, create_section_header, create_emoji_button

# Import emoji renderer for CTkImage support (Windows color emoji fix)
try:
    from .emoji_renderer import get_emoji_renderer, HAVE_PIL
    HAVE_EMOJI = HAVE_PIL and _CTK_AVAILABLE
except ImportError:
    HAVE_EMOJI = False
    get_emoji_renderer = None


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
# Custom Toggle Switch (CTk version)
# =============================================================================

class ToggleSwitch(tk.Canvas):
    """Custom toggle switch widget for non-CTk mode."""
    
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


# =============================================================================
# Settings Window (CTk version)
# =============================================================================

class SettingsWindow:
    """
    Standalone settings window using CustomTkinter.
    """
    
    def __init__(self, master=None):
        self.window_id = get_next_window_id()
        self.window_tag = f"settings_{self.window_id}"
        
        self.master = master
        self.colors = get_colors()
        self.root = None  # type: ignore
        self._destroyed = False
        
        # Config data
        self.config_data: Optional[ConfigData] = None
        self.original_config: Dict[str, Any] = {}
        
        # Widget references for saving
        self.widgets: Dict[str, Any] = {}
        self.vars: Dict[str, tk.Variable] = {}
        
        # Theme preview
        self.preview_frame: Optional[Any] = None
        
        # Determine if we can use CTk (must be in main thread)
        self.use_ctk = _can_use_ctk()
    
    def show(self, initial_tab: str = None):
        """
        Create and show the settings window.
        
        Args:
            initial_tab: Name of the tab to select initially (e.g. "API Keys")
        """
        # Sync CTk appearance mode only if we can use CTk
        if self.use_ctk:
            sync_ctk_appearance()
        
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
        
        self.root.title("AI Bridge Settings")
        self.root.geometry("1100x800")
        self.root.minsize(1000, 700)
        
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
        self.root.geometry(f"+{100 + offset}+{100 + offset}")
        
        # Main container
        main_container = ctk.CTkFrame(self.root, fg_color=self.colors.bg) if self.use_ctk else tk.Frame(self.root, bg=self.colors.bg)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Title bar
        self._create_title_bar(main_container)
        
        # Notebook (tabs)
        self._create_notebook(main_container)
        
        # Select initial tab if specified
        if initial_tab and self.use_ctk:
            try:
                self.tabview.set(initial_tab)
            except Exception:
                pass
        
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
            # Title with emoji image support
            title_text = "⚙️ Settings"
            title_label_kwargs = {
                "text": title_text,
                "font": get_ctk_font(24, "bold"),
                "text_color": self.colors.fg
            }
            
            if HAVE_EMOJI:
                renderer = get_emoji_renderer()
                emoji_img = renderer.get_ctk_image("⚙️", size=32)
                if emoji_img:
                    title_label_kwargs["text"] = "Settings"
                    title_label_kwargs["image"] = emoji_img
                    title_label_kwargs["compound"] = "left"
                    
            ctk.CTkLabel(
                title_frame,
                **title_label_kwargs
            ).pack(side="left")
            
            ctk.CTkLabel(
                title_frame,
                text="Edit config.ini",
                font=get_ctk_font(14),
                **get_ctk_label_colors(self.colors, muted=True)
            ).pack(side="left", padx=(20, 0))
        else:
            tk.Label(title_frame, text="⚙️ Settings",
                    font=("Segoe UI", 16, "bold"),
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            tk.Label(title_frame, text="Edit config.ini",
                    font=("Segoe UI", 10),
                    bg=self.colors.bg, fg=self.colors.blockquote).pack(side="left", padx=(15, 0))
    
    def _create_notebook(self, parent):
        """Create the tabbed notebook."""
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
            self.tabview.add("⚙️ General")
            self.tabview.add("🌐 Provider")
            self.tabview.add("⚡ Streaming")
            self.tabview.add("✏️ TextEditTool")
            self.tabview.add("🔑 API Keys")
            self.tabview.add("🔗 Endpoints")
            self.tabview.add("🎨 Theme")
            
            # Upgrade tabs with images and larger font
            upgrade_tabview_with_icons(self.tabview)
            
            self._create_general_tab(self.tabview.tab("⚙️ General"))
            self._create_provider_tab(self.tabview.tab("🌐 Provider"))
            self._create_streaming_tab(self.tabview.tab("⚡ Streaming"))
            self._create_textedit_tab(self.tabview.tab("✏️ TextEditTool"))
            self._create_keys_tab(self.tabview.tab("🔑 API Keys"))
            self._create_endpoints_tab(self.tabview.tab("🔗 Endpoints"))
            self._create_theme_tab(self.tabview.tab("🎨 Theme"))
        else:
            from tkinter import ttk
            style = ttk.Style(self.root)
            style.theme_use('clam')
            self.tabview = ttk.Notebook(parent)
            self.tabview.pack(fill="both", expand=True, pady=(0, 10))
            
            tabs = ["General", "Provider", "Streaming", "TextEditTool", "API Keys", "Endpoints", "Theme"]
            frames = {}
            for tab_name in tabs:
                frame = tk.Frame(self.tabview, bg=self.colors.bg)
                self.tabview.add(frame, text=tab_name)
                frames[tab_name] = frame
            
            self._create_general_tab(frames["General"])
            self._create_provider_tab(frames["Provider"])
            self._create_streaming_tab(frames["Streaming"])
            self._create_textedit_tab(frames["TextEditTool"])
            self._create_keys_tab(frames["API Keys"])
            self._create_endpoints_tab(frames["Endpoints"])
            self._create_theme_tab(frames["Theme"])
    
    def _create_general_tab(self, frame):
        """Create the General settings tab."""
        if self.use_ctk:
            scroll_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        else:
            scroll_frame = tk.Frame(frame, bg=self.colors.bg)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Server settings section
        create_section_header(scroll_frame, "🖥️ Server Settings", self.colors)
        
        # Host
        self._add_entry_field(scroll_frame, "host", "Host:",
                             self.config_data.config.get("host", "127.0.0.1"),
                             hint="⚠️ Restart required. IP address to bind.")
        
        # Port
        self._add_entry_field(scroll_frame, "port", "Port:",
                             str(self.config_data.config.get("port", 5000)),
                             hint="⚠️ Restart required. Port for Flask server (1-65535)")
        
        # Behavior section
        create_section_header(scroll_frame, "🧠 Behavior", self.colors, top_padding=20)
        
        # Show AI response in chat window
        self._add_toggle_field(scroll_frame, "show_ai_response_in_chat_window",
                              "Show AI response in chat window",
                              str(self.config_data.config.get("show_ai_response_in_chat_window", "no")).lower() == "yes",
                              hint="For endpoint requests. Actions/modifiers override this.")
        
        # Limits section
        create_section_header(scroll_frame, "🚦 Limits", self.colors, top_padding=20)
        
        # Max sessions
        self._add_spinbox_field(scroll_frame, "max_sessions", "Max sessions:",
                               self.config_data.config.get("max_sessions", 50),
                               1, 1000, hint="Maximum chat sessions to keep")
        
        # Max retries
        self._add_spinbox_field(scroll_frame, "max_retries", "Max retries:",
                               self.config_data.config.get("max_retries", 3),
                               0, 10, hint="Retries before giving up on API calls")
        
        # Retry delay
        self._add_spinbox_field(scroll_frame, "retry_delay", "Retry delay (s):",
                               self.config_data.config.get("retry_delay", 5),
                               1, 60, hint="Seconds to wait between retries")
        
        # Request timeout
        self._add_spinbox_field(scroll_frame, "request_timeout", "Request timeout (s):",
                               self.config_data.config.get("request_timeout", 120),
                               10, 600, hint="Timeout for API requests")
    
    def _create_provider_tab(self, frame):
        """Create the Provider settings tab."""
        if self.use_ctk:
            scroll_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        else:
            scroll_frame = tk.Frame(frame, bg=self.colors.bg)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Default provider
        create_section_header(scroll_frame, "🥇 Default Provider", self.colors)
        
        row = ctk.CTkFrame(scroll_frame, fg_color="transparent") if self.use_ctk else tk.Frame(scroll_frame, bg=self.colors.bg)
        row.pack(fill="x", pady=8)
        
        current_provider = self.config_data.config.get("default_provider", "google")
        self.vars["default_provider"] = tk.StringVar(master=self.root, value=current_provider)
        
        if self.use_ctk:
            ctk.CTkLabel(row, text="Provider:", font=get_ctk_font(13), width=160, anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(side="left")
            self.widgets["default_provider"] = ctk.CTkComboBox(
                row, variable=self.vars["default_provider"],
                values=["custom", "openrouter", "google"],
                width=220, height=32, state="readonly", font=get_ctk_font(13),
                **get_ctk_combobox_colors(self.colors)
            )
        else:
            from tkinter import ttk
            tk.Label(row, text="Provider:", font=("Segoe UI", 10), width=15, anchor="w",
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            self.widgets["default_provider"] = ttk.Combobox(
                row, textvariable=self.vars["default_provider"],
                values=["custom", "openrouter", "google"],
                state="readonly", width=25
            )
        self.widgets["default_provider"].pack(side="left", padx=(10, 0))
        
        # Custom provider settings
        create_section_header(scroll_frame, "🛠️ Custom Provider", self.colors, top_padding=20)
        
        self._add_entry_field(scroll_frame, "custom_url", "URL:",
                             self.config_data.config.get("custom_url", "") or "",
                             width=400)
        
        self._add_entry_field(scroll_frame, "custom_model", "Model:",
                             self.config_data.config.get("custom_model", "") or "",
                             width=300)
        
        # OpenRouter settings
        create_section_header(scroll_frame, "🚀 OpenRouter", self.colors, top_padding=20)
        
        self._add_entry_field(scroll_frame, "openrouter_model", "Model:",
                             self.config_data.config.get("openrouter_model", ""),
                             width=300)
        
        # Google settings
        create_section_header(scroll_frame, "💎 Google Gemini", self.colors, top_padding=20)
        
        self._add_entry_field(scroll_frame, "google_model", "Model:",
                             self.config_data.config.get("google_model", ""),
                             width=300)
    
    def _create_streaming_tab(self, frame):
        """Create the Streaming/Thinking settings tab."""
        if self.use_ctk:
            scroll_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        else:
            scroll_frame = tk.Frame(frame, bg=self.colors.bg)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Streaming section
        create_section_header(scroll_frame, "🌊 Streaming", self.colors)
        
        self._add_toggle_field(scroll_frame, "streaming_enabled",
                              "Enable streaming responses",
                              self.config_data.config.get("streaming_enabled", True))
        
        # Thinking section
        create_section_header(scroll_frame, "💭 Thinking / Reasoning", self.colors, top_padding=20)
        
        self._add_toggle_field(scroll_frame, "thinking_enabled",
                              "Enable thinking mode",
                              self.config_data.config.get("thinking_enabled", False))
        
        # Thinking output dropdown
        row = ctk.CTkFrame(scroll_frame, fg_color="transparent") if self.use_ctk else tk.Frame(scroll_frame, bg=self.colors.bg)
        row.pack(fill="x", pady=8)
        
        self.vars["thinking_output"] = tk.StringVar(
            master=self.root, value=self.config_data.config.get("thinking_output", "reasoning_content"))
        
        if self.use_ctk:
            ctk.CTkLabel(row, text="Thinking output:", font=get_ctk_font(13), width=180, anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(side="left")
            self.widgets["thinking_output"] = ctk.CTkComboBox(
                row, variable=self.vars["thinking_output"],
                values=["filter", "raw", "reasoning_content"],
                width=200, height=32, state="readonly", font=get_ctk_font(13),
                **get_ctk_combobox_colors(self.colors)
            )
        else:
            from tkinter import ttk
            tk.Label(row, text="Thinking output:", font=("Segoe UI", 10), width=18, anchor="w",
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            self.widgets["thinking_output"] = ttk.Combobox(
                row, textvariable=self.vars["thinking_output"],
                values=["filter", "raw", "reasoning_content"],
                state="readonly", width=20
            )
        self.widgets["thinking_output"].pack(side="left", padx=(10, 0))
        
        # Thinking config section
        create_section_header(scroll_frame, "Thinking Configuration", self.colors, top_padding=20)
        
        # Reasoning effort (OpenAI)
        row = ctk.CTkFrame(scroll_frame, fg_color="transparent") if self.use_ctk else tk.Frame(scroll_frame, bg=self.colors.bg)
        row.pack(fill="x", pady=8)
        
        self.vars["reasoning_effort"] = tk.StringVar(
            master=self.root, value=self.config_data.config.get("reasoning_effort", "high"))
        
        if self.use_ctk:
            ctk.CTkLabel(row, text="Reasoning effort (OpenAI):", font=get_ctk_font(13), width=200, anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(side="left")
            self.widgets["reasoning_effort"] = ctk.CTkComboBox(
                row, variable=self.vars["reasoning_effort"],
                values=["low", "medium", "high"],
                width=150, height=32, state="readonly", font=get_ctk_font(13),
                **get_ctk_combobox_colors(self.colors)
            )
        else:
            from tkinter import ttk
            tk.Label(row, text="Reasoning effort (OpenAI):", font=("Segoe UI", 10), width=22, anchor="w",
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            self.widgets["reasoning_effort"] = ttk.Combobox(
                row, textvariable=self.vars["reasoning_effort"],
                values=["low", "medium", "high"],
                state="readonly", width=12
            )
        self.widgets["reasoning_effort"].pack(side="left", padx=(10, 0))
        
        # Thinking budget (Gemini 2.5)
        self._add_spinbox_field(scroll_frame, "thinking_budget", "Thinking budget (Gemini 2.5):",
                               self.config_data.config.get("thinking_budget", -1),
                               -1, 100000)
        
        # Thinking level (Gemini 3.x)
        row = ctk.CTkFrame(scroll_frame, fg_color="transparent") if self.use_ctk else tk.Frame(scroll_frame, bg=self.colors.bg)
        row.pack(fill="x", pady=8)
        
        self.vars["thinking_level"] = tk.StringVar(
            master=self.root, value=self.config_data.config.get("thinking_level", "high"))
        
        if self.use_ctk:
            ctk.CTkLabel(row, text="Thinking level (Gemini 3.x):", font=get_ctk_font(13), width=200, anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(side="left")
            self.widgets["thinking_level"] = ctk.CTkComboBox(
                row, variable=self.vars["thinking_level"],
                values=["low", "high"],
                width=150, height=32, state="readonly", font=get_ctk_font(13),
                **get_ctk_combobox_colors(self.colors)
            )
        else:
            from tkinter import ttk
            tk.Label(row, text="Thinking level (Gemini 3.x):", font=("Segoe UI", 10), width=22, anchor="w",
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            self.widgets["thinking_level"] = ttk.Combobox(
                row, textvariable=self.vars["thinking_level"],
                values=["low", "high"],
                state="readonly", width=12
            )
        self.widgets["thinking_level"].pack(side="left", padx=(10, 0))
    
    def _create_textedit_tab(self, frame):
        """Create the TextEditTool settings tab."""
        if self.use_ctk:
            scroll_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        else:
            scroll_frame = tk.Frame(frame, bg=self.colors.bg)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Enable/Disable section
        create_section_header(scroll_frame, "✏️ TextEditTool", self.colors)
        
        self._add_toggle_field(scroll_frame, "text_edit_tool_enabled",
                              "Enable TextEditTool",
                              self.config_data.config.get("text_edit_tool_enabled", True),
                              hint="⚠️ Restart required")
        
        # Hotkeys section
        create_section_header(scroll_frame, "⌨️ Hotkeys", self.colors, top_padding=20)
        
        self._add_entry_field(scroll_frame, "text_edit_tool_hotkey", "Activation hotkey:",
                             self.config_data.config.get("text_edit_tool_hotkey", "ctrl+space"),
                             width=200, hint="⚠️ Restart required")
        
        self._add_entry_field(scroll_frame, "text_edit_tool_abort_hotkey", "Abort hotkey:",
                             self.config_data.config.get("text_edit_tool_abort_hotkey", "escape"),
                             width=200, hint="⚠️ Restart required")
        
        # Typing settings section
        create_section_header(scroll_frame, "🖱️ Typing Settings", self.colors, top_padding=20)
        
        self._add_spinbox_field(scroll_frame, "streaming_typing_delay", "Typing delay (ms):",
                               self.config_data.config.get("streaming_typing_delay", 5),
                               1, 100, hint="Delay per character in replace mode")
        
        self._add_toggle_field(scroll_frame, "streaming_typing_uncapped",
                              "Uncapped typing speed",
                              self.config_data.config.get("streaming_typing_uncapped", False),
                              hint="⚠️ No delay between chars. May overwhelm some apps.")
    
    def _create_keys_tab(self, frame):
        """Create the API Keys settings tab."""
        container = ctk.CTkFrame(frame, fg_color="transparent") if self.use_ctk else tk.Frame(frame, bg=self.colors.bg)
        container.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Create inner tabview for provider keys
        if self.use_ctk:
            keys_tabview = ctk.CTkTabview(
                container,
                fg_color=self.colors.bg,
                segmented_button_fg_color=self.colors.surface0,
                segmented_button_selected_color=self.colors.accent,
                segmented_button_unselected_color=self.colors.surface0,
                text_color=self.colors.fg
            )
            keys_tabview.pack(fill="both", expand=True)
            
            for provider in ["custom", "openrouter", "google"]:
                keys_tabview.add(provider.capitalize())
                self._create_keys_section(keys_tabview.tab(provider.capitalize()), provider)
        else:
            from tkinter import ttk
            keys_tabview = ttk.Notebook(container)
            keys_tabview.pack(fill="both", expand=True)
            
            for provider in ["custom", "openrouter", "google"]:
                frame_tab = tk.Frame(keys_tabview, bg=self.colors.bg)
                keys_tabview.add(frame_tab, text=provider.capitalize())
                self._create_keys_section(frame_tab, provider)
    
    def _create_keys_section(self, parent, provider: str):
        """Create a key management section for a provider."""
        container = ctk.CTkFrame(parent, fg_color="transparent") if self.use_ctk else tk.Frame(parent, bg=self.colors.bg)
        container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Instructions
        if self.use_ctk:
            ctk.CTkLabel(
                container,
                text=f"Manage {provider} API keys (keys are masked for security)",
                font=get_ctk_font(12),
                **get_ctk_label_colors(self.colors, muted=True)
            ).pack(anchor="w", pady=(0, 12))
        else:
            tk.Label(container, text=f"Manage {provider} API keys (keys are masked for security)",
                    font=("Segoe UI", 9), bg=self.colors.bg, fg=self.colors.blockquote).pack(anchor="w", pady=(0, 10))
        
        # Key list - Replace tk.Listbox with ScrollableButtonList
        if self.use_ctk:
            listbox = ScrollableButtonList(
                container, self.colors, command=None,
                corner_radius=8, fg_color=self.colors.input_bg
            )
        else:
            listbox = ScrollableButtonList(container, self.colors, command=None, bg=self.colors.input_bg)
        listbox.pack(fill="both", expand=True)
        
        def refresh_keys_list():
            listbox.clear()
            for i, key in enumerate(self.widgets[f"keys_{provider}_data"]):
                masked = self._mask_key(key)
                listbox.add_item(str(i), masked, "🔑")

        self.widgets[f"keys_{provider}_data"] = list(self.config_data.keys.get(provider, []))
        refresh_keys_list()
        
        self.widgets[f"keys_{provider}_listbox"] = listbox
        
        # Button frame
        btn_frame = ctk.CTkFrame(container, fg_color="transparent") if self.use_ctk else tk.Frame(container, bg=self.colors.bg)
        btn_frame.pack(fill="x", pady=(10, 0))
        
        # Add key entry
        if self.use_ctk:
            entry_var = tk.StringVar(master=self.root)
            key_entry = ctk.CTkEntry(
                btn_frame, textvariable=entry_var,
                font=get_ctk_font(12), width=400, height=36,
                placeholder_text="Paste new API key here...",
                **get_ctk_entry_colors(self.colors)
            )
        else:
            entry_var = tk.StringVar(master=self.root)
            key_entry = tk.Entry(btn_frame, textvariable=entry_var,
                                font=("Consolas", 10), width=40,
                                bg=self.colors.input_bg, fg=self.colors.fg)
            key_entry.insert(0, "Paste new API key here...")
            key_entry.configure(fg=self.colors.blockquote)
            
            def on_focus_in(e):
                if key_entry.get() == "Paste new API key here...":
                    key_entry.delete(0, "end")
                    key_entry.configure(fg=self.colors.fg)
            
            def on_focus_out(e):
                if not key_entry.get():
                    key_entry.insert(0, "Paste new API key here...")
                    key_entry.configure(fg=self.colors.blockquote)
            
            key_entry.bind('<FocusIn>', on_focus_in)
            key_entry.bind('<FocusOut>', on_focus_out)
        
        key_entry.pack(side="left", padx=(0, 10))
        
        def add_key():
            key = entry_var.get().strip()
            if key and key != "Paste new API key here...":
                self.widgets[f"keys_{provider}_data"].append(key)
                refresh_keys_list()
                entry_var.set("")
                if self.use_ctk:
                    key_entry.configure(placeholder_text="Paste new API key here...")
                else:
                    key_entry.insert(0, "Paste new API key here...")
                    key_entry.configure(fg=self.colors.blockquote)
        
        def remove_key():
            selected_id = listbox.get_selected()
            if selected_id:
                idx = int(selected_id)
                del self.widgets[f"keys_{provider}_data"][idx]
                refresh_keys_list()
        
        create_emoji_button(btn_frame, "Add", "", self.colors, "success", 80, 36, add_key).pack(side="left", padx=4)
        create_emoji_button(btn_frame, "Remove", "", self.colors, "danger", 90, 36, remove_key).pack(side="left", padx=4)
    
    def _upgrade_tabs(self, tabview):
        """Invoke internals to add images to tabs and increase font size."""
        # DEPRECATED: Use custom_widgets.upgrade_tabview_with_icons
        pass

    def _mask_key(self, key: str) -> str:
        """Mask an API key for display."""
        if len(key) <= 8:
            return "*" * len(key)
        return key[:4] + "..." + key[-4:]
    
    def _create_endpoints_tab(self, frame):
        """Create the Endpoints settings tab."""
        container = ctk.CTkFrame(frame, fg_color="transparent") if self.use_ctk else tk.Frame(frame, bg=self.colors.bg)
        container.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Left: endpoint list
        left_panel = ctk.CTkFrame(container, fg_color="transparent", width=240) if self.use_ctk else tk.Frame(container, bg=self.colors.bg, width=240)
        left_panel.pack(side="left", fill="y", padx=(0, 15))
        left_panel.pack_propagate(False)
        
        create_section_header(left_panel, "🔗 Endpoints", self.colors)
        
        # Endpoints List - Replace tk.Listbox with ScrollableButtonList
        if self.use_ctk:
            self.endpoint_listbox = ScrollableButtonList(
                left_panel, self.colors, command=self._on_endpoint_select,
                corner_radius=8, fg_color=self.colors.input_bg
            )
        else:
            self.endpoint_listbox = ScrollableButtonList(left_panel, self.colors, command=self._on_endpoint_select, bg=self.colors.input_bg)
        self.endpoint_listbox.pack(fill="both", expand=True)
        
        # Populate endpoints
        for name in sorted(self.config_data.endpoints.keys()):
            self.endpoint_listbox.add_item(name, name, "🔗")
        
        # Right: prompt editor
        right_panel = ctk.CTkFrame(container, fg_color="transparent") if self.use_ctk else tk.Frame(container, bg=self.colors.bg)
        right_panel.pack(side="left", fill="both", expand=True)
        
        if self.use_ctk:
            ctk.CTkLabel(right_panel, text="Prompt", font=get_ctk_font(14, "bold"),
                        text_color=self.colors.accent).pack(anchor="w", pady=(0, 12))
            
            self.endpoint_text = ctk.CTkTextbox(
                right_panel, font=get_ctk_font(12),
                **get_ctk_textbox_colors(self.colors)
            )
        else:
            tk.Label(right_panel, text="Prompt", font=("Segoe UI", 11, "bold"),
                    bg=self.colors.bg, fg=self.colors.accent).pack(anchor="w", pady=(0, 10))
            
            self.endpoint_text = tk.Text(
                right_panel, font=("Segoe UI", 10),
                bg=self.colors.input_bg, fg=self.colors.fg, wrap="word"
            )
        self.endpoint_text.pack(fill="both", expand=True, pady=(0, 10))
        
        # Button row
        btn_frame = ctk.CTkFrame(right_panel, fg_color="transparent") if self.use_ctk else tk.Frame(right_panel, bg=self.colors.bg)
        btn_frame.pack(fill="x")
        
        if self.use_ctk:
            ctk.CTkButton(
                btn_frame, text="Save Prompt", font=get_ctk_font(13),
                width=140, height=38, **get_ctk_button_colors(self.colors, "success"),
                command=self._save_endpoint
            ).pack(side="left", padx=4)
            
            self.endpoint_status = ctk.CTkLabel(btn_frame, text="", font=get_ctk_font(12),
                                               text_color=self.colors.accent_green)
        else:
            tk.Button(btn_frame, text="Save Prompt", font=("Segoe UI", 10),
                     bg=self.colors.accent_green, fg="#ffffff",
                     command=self._save_endpoint).pack(side="left", padx=2)
            self.endpoint_status = tk.Label(btn_frame, text="", font=("Segoe UI", 9),
                                           bg=self.colors.bg, fg=self.colors.accent_green)
        self.endpoint_status.pack(side="left", padx=15)
    
    def _on_endpoint_select(self, name):
        """Handle endpoint selection."""
        if name:
            prompt = self.config_data.endpoints.get(name, "")
            if self.use_ctk:
                self.endpoint_text.delete("0.0", "end")
                self.endpoint_text.insert("0.0", prompt)
            else:
                self.endpoint_text.delete("1.0", "end")
                self.endpoint_text.insert("1.0", prompt)
    
    def _save_endpoint(self):
        """Save the currently edited endpoint."""
        name = self.endpoint_listbox.get_selected()
        if name:
            if self.use_ctk:
                prompt = self.endpoint_text.get("0.0", "end").strip()
            else:
                prompt = self.endpoint_text.get("1.0", "end").strip()
            self.config_data.endpoints[name] = prompt
            if self.use_ctk:
                self.endpoint_status.configure(text=f"✅ Saved '{name}'", text_color=self.colors.accent_green)
            else:
                self.endpoint_status.configure(text=f"✅ Saved '{name}'", fg=self.colors.accent_green)
    
    def _create_theme_tab(self, frame):
        """Create the Theme settings tab."""
        if self.use_ctk:
            scroll_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        else:
            scroll_frame = tk.Frame(frame, bg=self.colors.bg)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Theme selection
        create_section_header(scroll_frame, "UI Theme", self.colors)
        
        # Theme dropdown
        row = ctk.CTkFrame(scroll_frame, fg_color="transparent") if self.use_ctk else tk.Frame(scroll_frame, bg=self.colors.bg)
        row.pack(fill="x", pady=8)
        
        current_theme = self.config_data.config.get("ui_theme", "catppuccin")
        self.vars["ui_theme"] = tk.StringVar(master=self.root, value=current_theme)
        
        if self.use_ctk:
            ctk.CTkLabel(row, text="Theme:", font=get_ctk_font(14), width=120, anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(side="left")
            self.widgets["ui_theme"] = ctk.CTkComboBox(
                row, variable=self.vars["ui_theme"],
                values=list_themes(), width=200, height=34, state="readonly", font=get_ctk_font(13),
                **get_ctk_combobox_colors(self.colors),
                command=lambda x: self._update_theme_preview()
            )
        else:
            from tkinter import ttk
            tk.Label(row, text="Theme:", font=("Segoe UI", 10), width=12, anchor="w",
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            self.widgets["ui_theme"] = ttk.Combobox(
                row, textvariable=self.vars["ui_theme"],
                values=list_themes(), state="readonly", width=20
            )
            self.widgets["ui_theme"].bind('<<ComboboxSelected>>', lambda e: self._update_theme_preview())
        self.widgets["ui_theme"].pack(side="left", padx=(10, 0))
        
        # Mode dropdown
        row = ctk.CTkFrame(scroll_frame, fg_color="transparent") if self.use_ctk else tk.Frame(scroll_frame, bg=self.colors.bg)
        row.pack(fill="x", pady=8)
        
        current_mode = self.config_data.config.get("ui_theme_mode", "auto")
        self.vars["ui_theme_mode"] = tk.StringVar(master=self.root, value=current_mode)
        
        if self.use_ctk:
            ctk.CTkLabel(row, text="Mode:", font=get_ctk_font(14), width=120, anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(side="left")
            self.widgets["ui_theme_mode"] = ctk.CTkComboBox(
                row, variable=self.vars["ui_theme_mode"],
                values=["auto", "dark", "light"], width=150, height=34, state="readonly", font=get_ctk_font(13),
                **get_ctk_combobox_colors(self.colors),
                command=lambda x: self._update_theme_preview()
            )
        else:
            from tkinter import ttk
            tk.Label(row, text="Mode:", font=("Segoe UI", 10), width=12, anchor="w",
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            self.widgets["ui_theme_mode"] = ttk.Combobox(
                row, textvariable=self.vars["ui_theme_mode"],
                values=["auto", "dark", "light"], state="readonly", width=12
            )
            self.widgets["ui_theme_mode"].bind('<<ComboboxSelected>>', lambda e: self._update_theme_preview())
        self.widgets["ui_theme_mode"].pack(side="left", padx=(10, 0))
        
        # Preview section
        create_section_header(scroll_frame, "Preview", self.colors, top_padding=20)
        
        # Preview frame
        if self.use_ctk:
            self.preview_frame = ctk.CTkFrame(
                scroll_frame, fg_color=self.colors.surface0,
                corner_radius=10, border_width=1, border_color=self.colors.border
            )
        else:
            self.preview_frame = tk.Frame(scroll_frame, bg=self.colors.surface0,
                                         highlightbackground=self.colors.border, highlightthickness=1)
        self.preview_frame.pack(fill="x", pady=5)
        
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
        if self.use_ctk:
            self.preview_frame.configure(fg_color=preview_colors.bg)
        else:
            self.preview_frame.configure(bg=preview_colors.bg)
        
        # Add sample elements
        inner = ctk.CTkFrame(self.preview_frame, fg_color="transparent") if self.use_ctk else tk.Frame(self.preview_frame, bg=preview_colors.bg)
        inner.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Title
        if self.use_ctk:
            ctk.CTkLabel(
                inner,
                text=f"Theme: {theme_name.title()} ({'Dark' if is_dark else 'Light'})",
                font=get_ctk_font(16, "bold"),
                text_color=preview_colors.fg
            ).pack(anchor="w")
            
            ctk.CTkLabel(
                inner,
                text="This is how text will look in this theme.",
                font=get_ctk_font(13),
                text_color=preview_colors.fg
            ).pack(anchor="w", pady=(8, 0))
            
            ctk.CTkLabel(
                inner,
                text="Muted/secondary text appears like this.",
                font=get_ctk_font(12),
                text_color=preview_colors.blockquote
            ).pack(anchor="w")
        else:
            tk.Label(inner, text=f"Theme: {theme_name.title()} ({'Dark' if is_dark else 'Light'})",
                    font=("Segoe UI", 12, "bold"),
                    bg=preview_colors.bg, fg=preview_colors.fg).pack(anchor="w")
            tk.Label(inner, text="This is how text will look in this theme.",
                    font=("Segoe UI", 10),
                    bg=preview_colors.bg, fg=preview_colors.fg).pack(anchor="w", pady=(5, 0))
            tk.Label(inner, text="Muted/secondary text appears like this.",
                    font=("Segoe UI", 9),
                    bg=preview_colors.bg, fg=preview_colors.blockquote).pack(anchor="w")
        
        # Sample buttons row
        btn_row = ctk.CTkFrame(inner, fg_color="transparent") if self.use_ctk else tk.Frame(inner, bg=preview_colors.bg)
        btn_row.pack(anchor="w", pady=(10, 0))
        
        for label, color in [("Primary", preview_colors.accent),
                            ("Success", preview_colors.accent_green),
                            ("Warning", preview_colors.accent_yellow),
                            ("Danger", preview_colors.accent_red)]:
            fg = "#ffffff" if label != "Warning" else "#000000"
            if self.use_ctk:
                ctk.CTkLabel(
                    btn_row, text=label, font=get_ctk_font(12),
                    fg_color=color, text_color=fg,
                    corner_radius=6, padx=14, pady=5
                ).pack(side="left", padx=4)
            else:
                tk.Label(btn_row, text=label, font=("Segoe UI", 9),
                        bg=color, fg=fg, padx=10, pady=3).pack(side="left", padx=2)
        
        # Sample input
        if self.use_ctk:
            sample_entry = ctk.CTkEntry(
                inner, font=get_ctk_font(12), width=240, height=34,
                fg_color=preview_colors.input_bg,
                text_color=preview_colors.fg,
                border_color=preview_colors.border
            )
            sample_entry.pack(anchor="w", pady=(12, 0))
            sample_entry.insert(0, "Sample input field")
        else:
            sample_entry = tk.Entry(inner, font=("Segoe UI", 10),
                                   bg=preview_colors.input_bg, fg=preview_colors.fg)
            sample_entry.insert(0, "Sample input field")
            sample_entry.pack(anchor="w", pady=(10, 0))
    
    # Helper methods for creating form fields
    
    def _add_entry_field(self, parent, key: str, label: str, value: str,
                        width: int = 240, hint: str = None):
        """Add an entry field to the form."""
        row = ctk.CTkFrame(parent, fg_color="transparent") if self.use_ctk else tk.Frame(parent, bg=self.colors.bg)
        row.pack(fill="x", pady=8)
        
        self.vars[key] = tk.StringVar(master=self.root, value=value)
        
        if self.use_ctk:
            ctk.CTkLabel(row, text=label, font=get_ctk_font(13), width=180, anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(side="left")
            entry = ctk.CTkEntry(
                row, textvariable=self.vars[key],
                font=get_ctk_font(13), width=width, height=34,
                **get_ctk_entry_colors(self.colors)
            )
            entry.pack(side="left", padx=(12, 0))
            self.widgets[key] = entry
            
            if hint:
                ctk.CTkLabel(row, text=hint, font=get_ctk_font(11),
                            **get_ctk_label_colors(self.colors, muted=True)).pack(side="left", padx=(15, 0))
        else:
            tk.Label(row, text=label, font=("Segoe UI", 10), width=18, anchor="w",
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            entry = tk.Entry(row, textvariable=self.vars[key],
                            font=("Segoe UI", 10), width=width//8,
                            bg=self.colors.input_bg, fg=self.colors.fg)
            entry.pack(side="left", padx=(10, 0), ipady=4)
            self.widgets[key] = entry
            
            if hint:
                tk.Label(row, text=hint, font=("Segoe UI", 9),
                        bg=self.colors.bg, fg=self.colors.blockquote).pack(side="left", padx=(15, 0))
    
    def _add_toggle_field(self, parent, key: str, label: str, value: bool, hint: str = None):
        """Add a toggle switch field to the form."""
        row = ctk.CTkFrame(parent, fg_color="transparent") if self.use_ctk else tk.Frame(parent, bg=self.colors.bg)
        row.pack(fill="x", pady=8)
        
        self.vars[key] = tk.BooleanVar(master=self.root, value=value)
        
        if self.use_ctk:
            self.widgets[key] = ctk.CTkSwitch(
                row, text=label, variable=self.vars[key],
                font=get_ctk_font(13), text_color=self.colors.fg,
                fg_color=self.colors.surface2,
                progress_color=self.colors.accent,
                button_color="#ffffff",
                button_hover_color="#f0f0f0"
            )
            self.widgets[key].pack(side="left")
            
            if hint:
                ctk.CTkLabel(row, text=hint, font=get_ctk_font(11),
                            **get_ctk_label_colors(self.colors, muted=True)).pack(side="left", padx=(15, 0))
        else:
            tk.Label(row, text=label, font=("Segoe UI", 10),
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            toggle = ToggleSwitch(row, self.vars[key], self.colors)
            toggle.pack(side="left", padx=(10, 0))
            self.widgets[key] = toggle
            
            if hint:
                tk.Label(row, text=hint, font=("Segoe UI", 9),
                        bg=self.colors.bg, fg=self.colors.blockquote).pack(side="left", padx=(15, 0))
    
    def _add_spinbox_field(self, parent, key: str, label: str, value: int,
                          min_val: int, max_val: int, hint: str = None):
        """Add a spinbox field to the form."""
        row = ctk.CTkFrame(parent, fg_color="transparent") if self.use_ctk else tk.Frame(parent, bg=self.colors.bg)
        row.pack(fill="x", pady=8)
        
        self.vars[key] = tk.IntVar(master=self.root, value=value)
        
        if self.use_ctk:
            ctk.CTkLabel(row, text=label, font=get_ctk_font(13), width=200, anchor="w",
                        **get_ctk_label_colors(self.colors)).pack(side="left")
            # CTk doesn't have spinbox, use entry
            entry = ctk.CTkEntry(
                row, textvariable=self.vars[key],
                font=get_ctk_font(13), width=100, height=34,
                **get_ctk_entry_colors(self.colors)
            )
            entry.pack(side="left", padx=(12, 0))
            self.widgets[key] = entry
            
            if hint:
                ctk.CTkLabel(row, text=hint, font=get_ctk_font(11),
                            **get_ctk_label_colors(self.colors, muted=True)).pack(side="left", padx=(15, 0))
        else:
            from tkinter import ttk
            tk.Label(row, text=label, font=("Segoe UI", 10), width=22, anchor="w",
                    bg=self.colors.bg, fg=self.colors.fg).pack(side="left")
            spinbox = ttk.Spinbox(row, textvariable=self.vars[key],
                                 from_=min_val, to=max_val, width=10)
            spinbox.pack(side="left", padx=(10, 0))
            self.widgets[key] = spinbox
            
            if hint:
                tk.Label(row, text=hint, font=("Segoe UI", 9),
                        bg=self.colors.bg, fg=self.colors.blockquote).pack(side="left", padx=(15, 0))
    
    def _create_button_bar(self, parent):
        """Create the bottom button bar."""
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent") if self.use_ctk else tk.Frame(parent, bg=self.colors.bg)
        btn_frame.pack(fill="x", pady=(10, 0))
        
        create_emoji_button(
            btn_frame, "Save", "💾", self.colors, "success", 120, 42, self._save
        ).pack(side="left", padx=6)
        
        create_emoji_button(
            btn_frame, "Cancel", "✖️", self.colors, "secondary", 110, 42, self._close
        ).pack(side="left", padx=6)
        
        if self.use_ctk:
             self.status_label = ctk.CTkLabel(
                btn_frame, text="", font=get_ctk_font(13),
                text_color=self.colors.accent_green
            )
        else:
            self.status_label = tk.Label(btn_frame, text="", font=("Segoe UI", 10),
                                        bg=self.colors.bg, fg=self.colors.accent_green)
        self.status_label.pack(side="left", padx=20)
    
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
            messagebox.showerror("Validation Error", error, parent=self.root)
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
            
            if self.use_ctk:
                self.status_label.configure(text="✅ Settings saved!", text_color=self.colors.accent_green)
            else:
                self.status_label.configure(text="✅ Settings saved!", fg=self.colors.accent_green)
            
            # Close after brief delay
            self.root.after(1500, self._close)
        else:
            if self.use_ctk:
                self.status_label.configure(text="❌ Failed to save", text_color=self.colors.accent_red)
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
    
    def __init__(self, parent_root):
        self.parent_root = parent_root
        # Run directly on GUI thread as a child window
        settings = SettingsWindow(master=parent_root)
        settings.show()


def create_attached_settings_window(parent_root):
    """Create a settings window (called on GUI thread)."""
    AttachedSettingsWindow(parent_root)


def show_settings_window():
    """Show settings window - can be called from any thread."""
    def run():
        settings = SettingsWindow()
        settings.show()
    
    threading.Thread(target=run, daemon=True).start()
