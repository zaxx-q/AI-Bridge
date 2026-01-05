# GUI package for CustomTkinter interface
# Uses CustomTkinter for modern UI with fallback to standard Tkinter

# Check for CustomTkinter availability
try:
    import customtkinter as ctk
    HAVE_CTK = True
except ImportError:
    HAVE_CTK = False

from .text_edit_tool import TextEditToolApp
from .core import (
    show_chat_gui, show_session_browser, get_gui_status, HAVE_GUI,
    show_settings_window, show_prompt_editor, GUICoordinator
)
from .themes import (
    ThemeRegistry, ThemeColors,
    get_colors, get_color_scheme, list_themes,
    get_ctk_button_colors, get_ctk_frame_colors,
    get_ctk_entry_colors, get_ctk_textbox_colors, get_ctk_scrollbar_colors,
    sync_ctk_appearance
)
from .utils import (
    copy_to_clipboard, render_markdown, setup_text_tags,
    get_tk_text_for_ctk_frame
)
from .popups import (
    create_typing_indicator, dismiss_typing_indicator,
    TypingIndicator
)

__all__ = [
    # Core exports
    'TextEditToolApp',
    'show_chat_gui',
    'show_session_browser',
    'get_gui_status',
    'HAVE_GUI',
    'HAVE_CTK',
    'show_settings_window',
    'show_prompt_editor',
    'GUICoordinator',
    
    # Theme system
    'ThemeRegistry',
    'ThemeColors',
    'get_colors',
    'get_color_scheme',
    'list_themes',
    'get_ctk_button_colors',
    'get_ctk_frame_colors',
    'get_ctk_entry_colors',
    'get_ctk_textbox_colors',
    'get_ctk_scrollbar_colors',
    'sync_ctk_appearance',
    
    # Utilities
    'copy_to_clipboard',
    'render_markdown',
    'setup_text_tags',
    'get_tk_text_for_ctk_frame',
    
    # Popups
    'create_typing_indicator',
    'dismiss_typing_indicator',
    'TypingIndicator',
]
