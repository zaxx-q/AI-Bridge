#!/usr/bin/env python3
"""
GUI utility functions for clipboard and markdown rendering

Uses tk.Text for markdown rendering (tag support not available in CTkTextbox).
This is the hybrid approach: CTk for windows/widgets, tk.Text for rich text display.

Emoji Support:
    On Windows, Tkinter doesn't natively render color emojis. This module
    integrates with emoji_renderer.py to replace emoji characters with
    inline PNG images from the Twemoji asset set.
"""

import re
import sys
import tkinter as tk
from tkinter import font as tkfont
from typing import Optional, Dict, Union, Tuple

# Import CustomTkinter with fallback
try:
    import customtkinter as ctk
    HAVE_CTK = True
except ImportError:
    HAVE_CTK = False
    ctk = None

# Import theme system
from .themes import (
    ThemeRegistry, ThemeColors,
    get_color_scheme as _get_color_scheme,
    is_dark_mode as _is_dark_mode,
    get_ctk_font
)

# Import emoji renderer
try:
    from .emoji_renderer import get_emoji_renderer, EmojiRenderer, HAVE_PIL
    HAVE_EMOJI_RENDERER = HAVE_PIL
except ImportError:
    HAVE_EMOJI_RENDERER = False
    get_emoji_renderer = None


def is_dark_mode() -> bool:
    """
    Check if system is in dark mode.
    
    This wraps the theme registry's dark mode detection,
    which respects the ui_theme_mode config setting.
    """
    return _is_dark_mode()


def get_color_scheme() -> Dict[str, str]:
    """
    Get color scheme based on current theme and mode.
    
    This uses the centralized ThemeRegistry which reads from config
    to determine the active theme and mode.
    
    Returns:
        Dict mapping color names to hex values
    """
    return _get_color_scheme()


def copy_to_clipboard(text: str, root = None) -> bool:
    """
    Cross-platform clipboard copy.
    
    Works with both tk.Tk and ctk.CTk root windows.
    """
    try:
        if root:
            # Both tk.Tk and ctk.CTk have clipboard methods
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()  # Required for clipboard to persist
            return True
        
        # Fallback to subprocess method
        if sys.platform == 'win32':
            import subprocess
            process = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-16le'))
        elif sys.platform == 'darwin':
            import subprocess
            process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
        else:
            try:
                import subprocess
                process = subprocess.Popen(['xclip', '-selection', 'clipboard'], stdin=subprocess.PIPE)
                process.communicate(text.encode('utf-8'))
            except:
                process = subprocess.Popen(['xsel', '--clipboard', '--input'], stdin=subprocess.PIPE)
                process.communicate(text.encode('utf-8'))
        return True
    except Exception as e:
        print(f"[Clipboard Error] {e}")
        return False


def setup_text_tags(text_widget: tk.Text, colors: Union[Dict[str, str], ThemeColors]):
    """
    Configure text tags for markdown styling with card-based message layout.
    
    Uses tk.Text tags which provide rich text formatting.
    This is why we keep tk.Text for chat display instead of CTkTextbox.
    
    Args:
        text_widget: A tk.Text widget (not CTkTextbox)
        colors: Color scheme dict or ThemeColors dataclass
    """
    # Convert ThemeColors to dict if needed
    if hasattr(colors, '__dataclass_fields__'):
        color_dict = {
            "header1": colors.accent,
            "header2": colors.accent,
            "header3": colors.accent,
            "fg": colors.fg,
            "code_bg": colors.surface0,
            "accent": colors.accent,
            "bullet": colors.accent,
            "blockquote": colors.blockquote,
            "user_accent": colors.user_accent,
            "assistant_accent": colors.assistant_accent,
            "user_bg": colors.user_bg,
            "assistant_bg": colors.assistant_bg,
            "border": colors.border,
            "accent_yellow": colors.accent_yellow,
            "overlay0": colors.overlay0,
            "surface1": colors.surface1,
            "select_bg": colors.accent,
            "select_fg": colors.bg,
        }
        colors = color_dict
    
    # Configure text selection colors
    select_bg = colors.get("select_bg", colors.get("accent", "#89b4fa"))
    select_fg = colors.get("select_fg", colors.get("bg", "#1e1e2e"))
    text_widget.configure(selectbackground=select_bg, selectforeground=select_fg)
    
    # Get available fonts with Segoe UI Emoji fallback for Windows
    try:
        if sys.platform == 'win32':
            mono_font = "Consolas"
            base_font = "Segoe UI"
        else:
            mono_font = "DejaVu Sans Mono"
            base_font = "DejaVu Sans"
    except:
        mono_font = "TkFixedFont"
        base_font = "TkDefaultFont"
    
    # Headers
    text_widget.tag_configure("h1",
        font=(base_font, 16, "bold"),
        foreground=colors["header1"],
        spacing1=6, spacing3=4)
    
    text_widget.tag_configure("h2",
        font=(base_font, 14, "bold"),
        foreground=colors["header2"],
        spacing1=5, spacing3=3)
    
    text_widget.tag_configure("h3",
        font=(base_font, 12, "bold"),
        foreground=colors["header3"],
        spacing1=4, spacing3=2)
    
    text_widget.tag_configure("h4",
        font=(base_font, 11, "bold"),
        foreground=colors["fg"],
        spacing1=3, spacing3=2)
    
    # Inline formatting
    text_widget.tag_configure("bold", font=(base_font, 11, "bold"))
    text_widget.tag_configure("italic", font=(base_font, 11, "italic"))
    text_widget.tag_configure("bold_italic", font=(base_font, 11, "bold italic"))
    text_widget.tag_configure("strikethrough", font=(base_font, 11), overstrike=True)
    
    # Code
    text_widget.tag_configure("code",
        font=(mono_font, 10),
        background=colors["code_bg"],
        foreground=colors["accent"])
    
    text_widget.tag_configure("codeblock",
        font=(mono_font, 10),
        background=colors["code_bg"],
        lmargin1=12, lmargin2=12, rmargin=8,
        spacing1=4, spacing3=4)
    
    # Lists
    text_widget.tag_configure("bullet",
        lmargin1=16, lmargin2=28,
        foreground=colors["fg"])
    
    text_widget.tag_configure("bullet_marker",
        foreground=colors["bullet"])
    
    text_widget.tag_configure("numbered",
        lmargin1=16, lmargin2=28,
        foreground=colors["fg"])
    
    # Blockquote
    text_widget.tag_configure("blockquote",
        lmargin1=16, lmargin2=20,
        foreground=colors["blockquote"],
        font=(base_font, 11, "italic"))
    
    # =================================================================
    # Card-style message blocks with accent bars
    # =================================================================
    
    # User message card - left accent bar color
    text_widget.tag_configure("user_accent_bar",
        foreground=colors["user_accent"],
        font=(base_font, 11))
    
    # User message label
    text_widget.tag_configure("user_label",
        font=(base_font, 11, "bold"),
        foreground=colors["user_accent"],
        background=colors["user_bg"],
        spacing1=0, spacing3=2)
    
    # User message content background
    text_widget.tag_configure("user_message",
        background=colors["user_bg"],
        lmargin1=0, lmargin2=0, rmargin=8,
        spacing1=0, spacing3=0)
    
    # Assistant message card - left accent bar color
    text_widget.tag_configure("assistant_accent_bar",
        foreground=colors["assistant_accent"],
        font=(base_font, 11))
    
    # Assistant message label
    text_widget.tag_configure("assistant_label",
        font=(base_font, 11, "bold"),
        foreground=colors["assistant_accent"],
        background=colors["assistant_bg"],
        spacing1=0, spacing3=2)
    
    # Assistant message content background
    text_widget.tag_configure("assistant_message",
        background=colors["assistant_bg"],
        lmargin1=0, lmargin2=0, rmargin=8,
        spacing1=0, spacing3=0)
    
    # Card gap (transparent space between messages)
    text_widget.tag_configure("card_gap",
        spacing1=4, spacing3=4,
        font=(base_font, 4))  # Small font for minimal height
    
    # Normal text
    text_widget.tag_configure("normal",
        font=(base_font, 11),
        foreground=colors["fg"])
    
    # Separator (only used within cards, not between them)
    text_widget.tag_configure("separator",
        foreground=colors.get("surface1", colors["border"]),
        spacing1=4, spacing3=4)
    
    # =================================================================
    # Thinking/Reasoning display - improved styling
    # =================================================================
    
    # Thinking header - clickable, yellow accent
    text_widget.tag_configure("thinking_header",
        font=(base_font, 10, "bold"),
        foreground=colors["accent_yellow"],
        spacing1=4, spacing3=2)
    
    # Add cursor change on hover for thinking header
    text_widget.tag_bind("thinking_header", "<Enter>",
        lambda e: text_widget.config(cursor="hand2"))
    text_widget.tag_bind("thinking_header", "<Leave>",
        lambda e: text_widget.config(cursor=""))
    
    # Thinking content - improved contrast (use overlay0 instead of blockquote)
    text_widget.tag_configure("thinking_content",
        font=(base_font, 10),
        foreground=colors.get("overlay0", colors["blockquote"]),
        lmargin1=12, lmargin2=12,
        spacing1=2, spacing3=2)
    
    # Thinking message role (for markdown-rendered thinking)
    text_widget.tag_configure("thinking_message",
        lmargin1=12, lmargin2=12, rmargin=8,
        spacing1=1, spacing3=2)


def render_markdown(text: str, text_widget: tk.Text, colors: Dict[str, str],
                   wrap: bool = True, as_role: Optional[str] = None,
                   enable_emojis: bool = True, block_tag: Optional[str] = None):
    """
    Render markdown text to a Tkinter Text widget with formatting.
    
    Args:
        text: The markdown text to render
        text_widget: The Tkinter Text widget to render into
        colors: Color scheme dictionary
        wrap: Whether to enable word wrapping
        as_role: Optional role ('user', 'assistant', or 'thinking') for message styling
        enable_emojis: Whether to render emojis as images (Windows only)
        block_tag: Optional additional tag to apply to all content (for card backgrounds)
    """
    # Setup tags if not already done
    setup_text_tags(text_widget, colors)
    
    # Configure wrap mode
    text_widget.configure(wrap=tk.WORD if wrap else tk.NONE)
    
    lines = text.split('\n')
    in_code_block = False
    code_block_lines = []
    
    # Apply role-based styling
    role_tag = None
    if as_role == "user":
        role_tag = "user_message"
    elif as_role == "assistant":
        role_tag = "assistant_message"
    elif as_role == "thinking":
        role_tag = "thinking_message"
    
    def build_tags(*primary_tags):
        """Build tag tuple including role_tag and block_tag if present."""
        result = list(primary_tags)
        if role_tag:
            result.append(role_tag)
        if block_tag:
            result.append(block_tag)
        return tuple(result) if result else None
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Code block handling
        if stripped.startswith('```'):
            if in_code_block:
                # End code block - render accumulated lines
                if code_block_lines:
                    code_text = '\n'.join(code_block_lines)
                    tags = build_tags("codeblock")
                    # Don't render emojis in code blocks
                    text_widget.insert(tk.END, code_text + '\n', tags)
                code_block_lines = []
                in_code_block = False
            else:
                # Start code block
                in_code_block = True
            continue
        
        if in_code_block:
            code_block_lines.append(line)
            continue
        
        # Add newline between lines (except first)
        if text_widget.index(tk.END) != "1.0" and i > 0:
            newline_tags = build_tags("normal")
            text_widget.insert(tk.END, '\n', newline_tags)
        
        # Empty line - minimal spacing
        if not stripped:
            empty_tags = build_tags("normal")
            text_widget.insert(tk.END, '\n', empty_tags)
            continue
        
        # Headers
        if stripped.startswith('#'):
            level = 0
            for char in stripped:
                if char == '#':
                    level += 1
                else:
                    break
            
            if level <= 6 and len(stripped) > level and stripped[level] == ' ':
                content = stripped[level+1:]
                tag = f"h{min(level, 4)}"
                tags = build_tags(tag)
                _insert_with_emojis(text_widget, content, tags, enable_emojis)
                continue
        
        # Blockquote
        if stripped.startswith('>'):
            content = stripped[1:].strip()
            tags = build_tags("blockquote")
            _insert_with_emojis(text_widget, "│ " + content, tags, enable_emojis)
            continue
        
        # Bullet points
        if stripped.startswith('- ') or stripped.startswith('* '):
            content = stripped[2:]
            # Insert bullet marker
            tags = build_tags("bullet_marker")
            text_widget.insert(tk.END, "  • ", tags)
            # Insert content with inline formatting
            _render_inline(content, text_widget, colors, role_tag, enable_emojis, block_tag)
            continue
        
        # Numbered list
        match = re.match(r'^(\d+)\.\s+(.+)$', stripped)
        if match:
            num, content = match.groups()
            tags = build_tags("numbered")
            text_widget.insert(tk.END, f"  {num}. ", tags)
            _render_inline(content, text_widget, colors, role_tag, enable_emojis, block_tag)
            continue
        
        # Horizontal rule
        if re.match(r'^[-*_]{3,}$', stripped):
            tags = build_tags("separator")
            text_widget.insert(tk.END, "─" * 40, tags)
            continue
        
        # Regular paragraph with inline formatting
        _render_inline(line, text_widget, colors, role_tag, enable_emojis, block_tag)
    
    # Flush any remaining code block
    if in_code_block and code_block_lines:
        code_text = '\n'.join(code_block_lines)
        tags = build_tags("codeblock")
        # Don't render emojis in code blocks
        text_widget.insert(tk.END, code_text + '\n', tags)


def _insert_with_emojis(
    text_widget: tk.Text,
    text: str,
    tags: Optional[Tuple[str, ...]] = None,
    enable_emojis: bool = True
):
    """
    Insert text into a Text widget, optionally rendering emojis as images.
    
    On Windows, this replaces emoji characters with inline PNG images
    for proper color emoji display. On other platforms or if the emoji
    renderer is not available, falls back to plain text insertion.
    
    Args:
        text_widget: The tk.Text widget
        text: Text to insert
        tags: Tags to apply to the text
        enable_emojis: Whether to render emojis as images (default True)
    """
    # Only use emoji rendering on Windows and if available
    use_emoji_renderer = (
        enable_emojis and
        HAVE_EMOJI_RENDERER and
        sys.platform == 'win32' and
        get_emoji_renderer is not None
    )
    
    if use_emoji_renderer:
        try:
            renderer = get_emoji_renderer()
            renderer.insert_text_with_emojis(text_widget, text, tags)
        except Exception:
            # Fallback on any error
            text_widget.insert(tk.END, text, tags)
    else:
        text_widget.insert(tk.END, text, tags)


def _render_inline(text: str, text_widget: tk.Text, colors: Dict[str, str],
                   role_tag: Optional[str] = None, enable_emojis: bool = True,
                   block_tag: Optional[str] = None):
    """Render inline markdown formatting (bold, italic, code) with emoji support."""
    
    def build_tags(*primary_tags):
        """Build tag tuple including role_tag and block_tag if present."""
        result = list(primary_tags)
        if role_tag:
            result.append(role_tag)
        if block_tag:
            result.append(block_tag)
        return tuple(result) if result else ("normal",)
    
    # Pattern for inline elements
    # Order matters: check bold+italic first, then bold, then italic, then code, then strikethrough
    patterns = [
        (r'\*\*\*(.+?)\*\*\*', 'bold_italic'),  # ***text***
        (r'___(.+?)___', 'bold_italic'),         # ___text___
        (r'\*\*(.+?)\*\*', 'bold'),              # **text**
        (r'__(.+?)__', 'bold'),                  # __text__
        (r'\*(.+?)\*', 'italic'),                # *text*
        (r'_(.+?)_', 'italic'),                  # _text_ (word boundary aware)
        (r'`([^`]+)`', 'code'),                  # `code`
        (r'~~(.+?)~~', 'strikethrough'),         # ~~text~~
    ]
    
    # Build a combined pattern to find all matches in order
    combined = r'(\*\*\*.+?\*\*\*|___.+?___|' \
               r'\*\*.+?\*\*|__.+?__|' \
               r'\*[^\*]+\*|(?<![a-zA-Z])_[^_]+_(?![a-zA-Z])|' \
               r'`[^`]+`|~~.+?~~)'
    
    pos = 0
    for match in re.finditer(combined, text):
        # Insert any text before this match
        if match.start() > pos:
            plain_text = text[pos:match.start()]
            tags = build_tags("normal")
            _insert_with_emojis(text_widget, plain_text, tags, enable_emojis)
        
        matched_text = match.group(0)
        content = None
        tag = "normal"
        
        # Determine which pattern matched
        if matched_text.startswith('***') and matched_text.endswith('***'):
            content = matched_text[3:-3]
            tag = "bold_italic"
        elif matched_text.startswith('___') and matched_text.endswith('___'):
            content = matched_text[3:-3]
            tag = "bold_italic"
        elif matched_text.startswith('**') and matched_text.endswith('**'):
            content = matched_text[2:-2]
            tag = "bold"
        elif matched_text.startswith('__') and matched_text.endswith('__'):
            content = matched_text[2:-2]
            tag = "bold"
        elif matched_text.startswith('`') and matched_text.endswith('`'):
            content = matched_text[1:-1]
            tag = "code"
        elif matched_text.startswith('~~') and matched_text.endswith('~~'):
            content = matched_text[2:-2]
            tag = "strikethrough"
        elif matched_text.startswith('*') and matched_text.endswith('*'):
            content = matched_text[1:-1]
            tag = "italic"
        elif matched_text.startswith('_') and matched_text.endswith('_'):
            content = matched_text[1:-1]
            tag = "italic"
        
        if content:
            tags = build_tags(tag)
            _insert_with_emojis(text_widget, content, tags, enable_emojis)
        
        pos = match.end()
    
    # Insert any remaining text
    if pos < len(text):
        remaining = text[pos:]
        tags = build_tags("normal")
        _insert_with_emojis(text_widget, remaining, tags, enable_emojis)


def render_plain_text(text: str, text_widget: tk.Text, wrap: bool = True):
    """Render plain text (markdown stripped) to a Text widget"""
    from ..utils import strip_markdown
    plain = strip_markdown(text)
    text_widget.configure(wrap=tk.WORD if wrap else tk.NONE)
    text_widget.insert(tk.END, plain)


def get_tk_text_for_ctk_frame(parent_frame, colors: Union[Dict[str, str], ThemeColors], **kwargs) -> tk.Text:
    """
    Create a tk.Text widget properly styled to look good inside a CTkFrame.
    
    This helper creates a tk.Text with theme-appropriate colors and styling
    that visually integrates with CustomTkinter frames.
    
    Args:
        parent_frame: A CTkFrame or tk.Frame to place the text widget in
        colors: Color scheme dict or ThemeColors dataclass
        **kwargs: Additional arguments passed to tk.Text
        
    Returns:
        Configured tk.Text widget
    """
    # Get color values
    if hasattr(colors, '__dataclass_fields__'):
        bg = colors.text_bg
        fg = colors.fg
        insert_bg = colors.fg
        select_bg = colors.accent
    else:
        bg = colors.get("text_bg", "#1e1e2e")
        fg = colors.get("fg", "#cdd6f4")
        insert_bg = fg
        select_bg = colors.get("accent", "#89b4fa")
    
    # Default font
    if sys.platform == 'win32':
        font = ("Segoe UI", 11)
    else:
        font = ("DejaVu Sans", 11)
    
    # Merge with provided kwargs
    text_kwargs = {
        "wrap": tk.WORD,
        "font": font,
        "bg": bg,
        "fg": fg,
        "insertbackground": insert_bg,
        "selectbackground": select_bg,
        "relief": tk.FLAT,
        "highlightthickness": 0,
        "borderwidth": 0,
        "padx": 12,
        "pady": 12,
    }
    text_kwargs.update(kwargs)
    
    return tk.Text(parent_frame, **text_kwargs)
