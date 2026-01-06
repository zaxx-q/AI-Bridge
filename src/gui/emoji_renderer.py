#!/usr/bin/env python3
"""
Emoji Renderer for Tkinter and CustomTkinter widgets

Replaces emoji characters with inline PNG images from the Twemoji asset set.
This is necessary because Windows Tkinter doesn't natively render color emojis
in Text widgets - they appear as monochrome outlines.

Supports two rendering modes:
1. tk.Text widgets: Uses image_create() to embed PhotoImage objects
2. CTkButton/CTkLabel: Uses CTkImage with compound="left" layout

The assets should be placed in assets/emojis/72x72/ with filenames matching
the Unicode codepoints in lowercase hex (e.g., 1f600.png for 😀).

For multi-codepoint emojis (like flags 🇺🇸), filenames use hyphens:
1f1fa-1f1f8.png
"""

import os
import re
import sys
import zipfile
import io
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Any
import tkinter as tk

# Try to import PIL for image handling
try:
    from PIL import Image, ImageTk
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

# Try to import CustomTkinter for CTkImage support
try:
    import customtkinter as ctk
    from customtkinter import CTkImage
    HAVE_CTK = True
except ImportError:
    HAVE_CTK = False
    CTkImage = None


def get_assets_path() -> Tuple[Path, bool]:
    """
    Get the path to the emoji assets (zip or directory).
    
    Returns:
        Tuple[Path, bool]: (path, is_zip)
    """
    # Potential paths to check
    paths = []
    
    # 1. Relative to this file (development)
    module_dir = Path(__file__).parent.parent.parent
    assets_base = module_dir / "assets"
    paths.append(assets_base / "emojis.zip")
    paths.append(assets_base / "emojis" / "72x72")
    
    # 2. Relative to sys.executable (frozen executable)
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        assets_base = exe_dir / "assets"
        paths.append(assets_base / "emojis.zip")
        paths.append(assets_base / "emojis" / "72x72")
    
    # 3. Current working directory
    cwd_base = Path.cwd() / "assets"
    paths.append(cwd_base / "emojis.zip")
    paths.append(cwd_base / "emojis" / "72x72")
    
    for path in paths:
        if path.exists():
            return path, path.suffix == '.zip'
    
    # Default fallback
    return Path("assets/emojis.zip"), True


# Regex patterns for emoji detection
# This covers most common emoji ranges including:
# - Basic emoticons (U+1F600-U+1F64F)
# - Misc symbols (U+2600-U+26FF)
# - Dingbats (U+2700-U+27BF)
# - Transport and map symbols (U+1F680-U+1F6FF)
# - Supplemental symbols (U+1F900-U+1F9FF)
# - Regional indicators for flags (U+1F1E0-U+1F1FF)
# - Various other emoji blocks

# Pattern to match emoji characters and sequences
# This is a simplified pattern that catches most emojis
EMOJI_PATTERN = re.compile(
    r'[\U0001F600-\U0001F64F]'  # Emoticons
    r'|[\U0001F300-\U0001F5FF]'  # Misc Symbols and Pictographs
    r'|[\U0001F680-\U0001F6FF]'  # Transport and Map
    r'|[\U0001F700-\U0001F77F]'  # Alchemical Symbols
    r'|[\U0001F780-\U0001F7FF]'  # Geometric Shapes Extended
    r'|[\U0001F800-\U0001F8FF]'  # Supplemental Arrows-C
    r'|[\U0001F900-\U0001F9FF]'  # Supplemental Symbols and Pictographs
    r'|[\U0001FA00-\U0001FA6F]'  # Chess Symbols
    r'|[\U0001FA70-\U0001FAFF]'  # Symbols and Pictographs Extended-A
    r'|[\U00002702-\U000027B0]'  # Dingbats
    r'|[\U0001F1E0-\U0001F1FF]'  # Regional indicators (flags)
    r'|[\U00002600-\U000026FF]'  # Misc symbols
    r'|[\U00002300-\U000023FF]'  # Misc Technical
    r'|[\U0000231A-\U0000231B]'  # Watch, Hourglass
    r'|[\U00002B50]'              # Star
    r'|[\U00003030]'              # Wavy dash
    r'|[\U0000303D]'              # Part alternation mark
    r'|[\U00002934-\U00002935]'  # Arrows
    r'|[\U000025AA-\U000025AB]'  # Squares
    r'|[\U000025B6]'              # Play button
    r'|[\U000025C0]'              # Reverse button
    r'|[\U000025FB-\U000025FE]'  # Squares
    r'|[\U00002B05-\U00002B07]'  # Arrows
    r'|[\U00002B1B-\U00002B1C]'  # Squares
    r'|[\U00002B55]'              # Circle
)

# Pattern for flag emoji sequences (regional indicator pairs)
FLAG_PATTERN = re.compile(r'[\U0001F1E6-\U0001F1FF]{2}')

# Pattern for ZWJ sequences (emoji joined with zero-width joiner)
# These are complex emojis like family emojis, professions with skin tones, etc.
ZWJ = '\u200d'
VARIATION_SELECTOR = '\ufe0f'


class EmojiRenderer:
    """
    Renders emojis as inline images in Tkinter and CustomTkinter widgets.
    
    Usage for tk.Text:
        renderer = EmojiRenderer()
        renderer.insert_text_with_emojis(text_widget, "Hello 😀 World!", tags=("normal",))
    
    Usage for CTkButton/CTkLabel:
        renderer = EmojiRenderer()
        content = renderer.prepare_widget_content("📋 Sessions", size=18)
        button = CTkButton(parent, text=content["text"], image=content["image"], compound=content["compound"])
    """
    
    DEFAULT_SIZE = 18  # Default emoji size in pixels
    CTK_DEFAULT_SIZE = 18  # Default size for CTkImage buttons
    
    def __init__(self, size: int = None):
        """
        Initialize the emoji renderer.
        
        Args:
            size: Size to render emojis at in pixels (default: 18)
        """
        self.assets_path, self.is_zip = get_assets_path()
        self.size = size or self.DEFAULT_SIZE
        
        # ZIP file handling
        self.zip_file: Optional[zipfile.ZipFile] = None
        self.zip_data: Optional[bytes] = None
        
        if self.is_zip and self.assets_path.exists():
            try:
                # Read entire ZIP into RAM
                with open(self.assets_path, "rb") as f:
                    self.zip_data = f.read()
                self.zip_file = zipfile.ZipFile(io.BytesIO(self.zip_data))
            except Exception as e:
                print(f"[Error] Failed to load emoji zip: {e}")
        
        # Cache for PhotoImage (tk.Text widgets)
        self._cache: Dict[Tuple[str, int], ImageTk.PhotoImage] = {}
        
        # Cache for CTkImage (CTkButton/CTkLabel widgets)
        self._ctk_cache: Dict[Tuple[str, int], Any] = {}
        
        # Track missing files to avoid repeated lookups
        self._missing_cache: set = set()
        
        # Check if PIL is available
        if not HAVE_PIL:
            print("[Warning] PIL not available - emoji rendering disabled")
    
    def get_codepoint_filename(self, char_or_seq: str) -> str:
        """
        Convert an emoji character or sequence to its Twemoji filename.
        
        Single emojis: 😀 -> "1f600"
        Flag pairs: 🇺🇸 -> "1f1fa-1f1f8"
        ZWJ sequences: 👨‍👩‍👧 -> "1f468-200d-1f469-200d-1f467"
        
        Args:
            char_or_seq: The emoji character(s)
            
        Returns:
            The filename without extension (e.g., "1f600")
        """
        # Remove variation selectors for lookup
        clean = char_or_seq.replace(VARIATION_SELECTOR, '')
        
        # Convert each codepoint to hex and join with hyphens
        codepoints = []
        for char in clean:
            cp = ord(char)
            # Skip if it's a combining character we don't want
            if cp == 0xfe0f:  # Variation selector
                continue
            codepoints.append(f"{cp:x}")
        
        return "-".join(codepoints)
    
    def _load_pil_image(self, emoji: str) -> Optional[Image.Image]:
        """
        Load PIL Image for an emoji from assets.
        
        Args:
            emoji: The emoji character(s)
            
        Returns:
            PIL Image if found, None otherwise
        """
        if not HAVE_PIL:
            return None
        
        filename = self.get_codepoint_filename(emoji)
        
        # Check if we already know this file is missing
        if filename in self._missing_cache:
            return None
        
        # Try to load the image
        # Try finding image in ZIP or directory
        try:
            name_variants = [f"{filename}.png", f"{filename.lower()}.png"]
            
            if self.is_zip and self.zip_file:
                # Look in ZIP
                found_name = None
                for name in name_variants:
                    if name in self.zip_file.namelist():
                        found_name = name
                        break
                
                if found_name:
                    with self.zip_file.open(found_name) as f:
                        # Must read into memory because Image.open is lazy
                        # and the zip file handle will close when we exit the block
                        img_data = f.read()
                        return Image.open(io.BytesIO(img_data))
            
            elif not self.is_zip and self.assets_path.exists():
                # Look in directory
                for name in name_variants:
                    image_path = self.assets_path / name
                    if image_path.exists():
                        return Image.open(image_path)
        
        except Exception:
            pass
            
        self._missing_cache.add(filename)
        return None
    
    def get_emoji_image(self, emoji: str, size: Optional[int] = None) -> Optional[ImageTk.PhotoImage]:
        """
        Load and cache an emoji image as PhotoImage (for tk.Text widgets).
        
        Args:
            emoji: The emoji character(s)
            size: Size in pixels (uses default if not specified)
            
        Returns:
            PhotoImage if found, None otherwise
        """
        if not HAVE_PIL:
            return None
        
        size = size or self.size
        filename = self.get_codepoint_filename(emoji)
        cache_key = (filename, size)
        
        # Check cache
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Load PIL image
        pil_image = self._load_pil_image(emoji)
        if pil_image is None:
            return None
        
        try:
            # Resize
            pil_image = pil_image.resize((size, size), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(pil_image)
            
            # Cache it (IMPORTANT: must keep reference to prevent garbage collection)
            self._cache[cache_key] = photo
            
            return photo
            
        except Exception:
            return None
    
    def get_ctk_image(self, emoji: str, size: Optional[int] = None) -> Optional[Any]:
        """
        Load and cache an emoji as CTkImage (for CTkButton/CTkLabel widgets).
        
        CTkImage provides:
        - Automatic DPI scaling (crisp on 4K monitors)
        - Theme-aware rendering
        
        Args:
            emoji: The emoji character(s)
            size: Size in pixels (uses CTK_DEFAULT_SIZE if not specified)
            
        Returns:
            CTkImage if found and CTk available, None otherwise
        """
        if not HAVE_PIL or not HAVE_CTK:
            return None
        
        size = size or self.CTK_DEFAULT_SIZE
        filename = self.get_codepoint_filename(emoji)
        cache_key = (f"ctk_{filename}", size)
        
        # Check cache
        if cache_key in self._ctk_cache:
            return self._ctk_cache[cache_key]
        
        # Load PIL image
        pil_image = self._load_pil_image(emoji)
        if pil_image is None:
            return None
        
        try:
            # CTkImage handles resizing internally
            # Use same image for both light and dark modes (emojis don't change)
            ctk_img = CTkImage(
                light_image=pil_image,
                dark_image=pil_image,
                size=(size, size)
            )
            
            # Cache it
            self._ctk_cache[cache_key] = ctk_img
            
            return ctk_img
            
        except Exception:
            return None
    
    def extract_leading_emoji(self, text: str) -> Tuple[Optional[str], str]:
        """
        Extract a leading emoji from text.
        
        Args:
            text: Text that may start with an emoji
            
        Returns:
            Tuple of (emoji_string, remaining_text) or (None, original_text)
            
        Examples:
            "📋 Sessions" -> ("📋", "Sessions")
            "Hello" -> (None, "Hello")
            "🇺🇸 USA" -> ("🇺🇸", "USA")
        """
        text = text.strip()
        if not text:
            return None, text
        
        # Check for flag emoji first (two regional indicators)
        if len(text) >= 2:
            match = FLAG_PATTERN.match(text)
            if match:
                emoji = match.group()
                remaining = text[len(emoji):].lstrip()
                return emoji, remaining
        
        # Check single emoji at start
        match = EMOJI_PATTERN.match(text)
        if match:
            emoji = match.group()
            remaining = text[len(emoji):].lstrip()
            return emoji, remaining
        
        return None, text
    
    def prepare_widget_content(
        self,
        text: str,
        size: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Prepare content for CTkButton/CTkLabel with emoji support.
        
        Extracts leading emoji and returns kwargs for widget creation.
        
        Args:
            text: Text that may contain a leading emoji (e.g., "📋 Sessions")
            size: Emoji size in pixels (default: 18)
            
        Returns:
            Dict with keys:
                - "text": str - The text without the emoji
                - "image": CTkImage|None - The emoji image if found
                - "compound": str|None - "left" if image present, else None
                
        Usage:
            content = renderer.prepare_widget_content("📋 Sessions")
            button = CTkButton(parent, **content, ...)
        """
        size = size or self.CTK_DEFAULT_SIZE
        
        # Extract leading emoji
        emoji, remaining_text = self.extract_leading_emoji(text)
        
        if emoji:
            # Try to get CTkImage for the emoji
            ctk_img = self.get_ctk_image(emoji, size)
            
            if ctk_img:
                return {
                    "text": remaining_text,
                    "image": ctk_img,
                    "compound": "left"
                }
        
        # No emoji or couldn't load image - return original text
        return {
            "text": text,
            "image": None,
            "compound": None
        }
    
    def find_emojis(self, text: str) -> List[Tuple[int, int, str]]:
        """
        Find all emoji positions in text.
        
        Args:
            text: The text to search
            
        Returns:
            List of (start, end, emoji_string) tuples
        """
        results = []
        
        # First, find flag sequences (two regional indicators)
        for match in FLAG_PATTERN.finditer(text):
            results.append((match.start(), match.end(), match.group()))
        
        # Then find individual emojis
        for match in EMOJI_PATTERN.finditer(text):
            start, end = match.start(), match.end()
            
            # Skip if this position is already covered by a flag
            if any(r[0] <= start < r[1] for r in results):
                continue
            
            results.append((start, end, match.group()))
        
        # Sort by position
        results.sort(key=lambda x: x[0])
        
        return results
    
    def insert_text_with_emojis(
        self, 
        text_widget: tk.Text, 
        text: str, 
        tags: Optional[Tuple[str, ...]] = None,
        at_end: bool = True
    ):
        """
        Insert text into a Text widget, replacing emojis with images.
        
        Args:
            text_widget: The tk.Text widget
            text: Text to insert
            tags: Tags to apply to non-emoji text
            at_end: If True, insert at end; otherwise at current cursor
        """
        if not HAVE_PIL:
            # Fallback: just insert text normally
            if at_end:
                text_widget.insert(tk.END, text, tags)
            else:
                text_widget.insert(tk.INSERT, text, tags)
            return
        
        # Find emojis
        emojis = self.find_emojis(text)
        
        if not emojis:
            # No emojis, just insert text
            if at_end:
                text_widget.insert(tk.END, text, tags)
            else:
                text_widget.insert(tk.INSERT, text, tags)
            return
        
        # Insert text segments and emojis
        pos = tk.END if at_end else tk.INSERT
        last_end = 0
        
        for start, end, emoji in emojis:
            # Insert text before this emoji
            if start > last_end:
                text_widget.insert(pos, text[last_end:start], tags)
            
            # Try to get emoji image
            img = self.get_emoji_image(emoji)
            
            if img:
                # Insert the image
                text_widget.image_create(pos, image=img)
            else:
                # Fallback: insert the emoji character as text
                text_widget.insert(pos, emoji, tags)
            
            last_end = end
        
        # Insert remaining text after last emoji
        if last_end < len(text):
            text_widget.insert(pos, text[last_end:], tags)
    
    def clear_cache(self):
        """Clear all image caches."""
        self._cache.clear()
        self._ctk_cache.clear()
        self._missing_cache.clear()
    
    def preload_common_emojis(self):
        """Preload commonly used emojis into cache."""
        common_emojis = [
            "😀", "😃", "😄", "😁", "😆", "😅", "🤣", "😂",
            "🙂", "🙃", "😉", "😊", "😇", "🥰", "😍", "🤩",
            "😘", "😗", "☺", "😚", "😙", "🥲", "😋", "😛",
            "✅", "❌", "⚠️", "❓", "❗", "💡", "🔥", "⭐",
            "📋", "📂", "📡", "🤖", "🌊", "💭", "🔑", "🚀",
            "🖥️", "⚙️", "✏️", "🔲", "📟", "🔄", "🗑️", "💬",
            "👍", "👎", "👏", "🙌", "🤝", "🙏", "✍️", "💪",
        ]
        
        for emoji in common_emojis:
            self.get_emoji_image(emoji)


# Global renderer instance
_global_renderer: Optional[EmojiRenderer] = None


def get_emoji_renderer() -> EmojiRenderer:
    """Get the global emoji renderer instance."""
    global _global_renderer
    if _global_renderer is None:
        _global_renderer = EmojiRenderer()
    return _global_renderer


def insert_with_emojis(
    text_widget: tk.Text,
    text: str,
    tags: Optional[Tuple[str, ...]] = None
):
    """
    Convenience function to insert text with emoji rendering (for tk.Text).
    
    Args:
        text_widget: The tk.Text widget
        text: Text to insert (may contain emojis)
        tags: Tags to apply to non-emoji text
    """
    renderer = get_emoji_renderer()
    renderer.insert_text_with_emojis(text_widget, text, tags)


def get_ctk_emoji_image(emoji: str, size: int = 18) -> Optional[Any]:
    """
    Convenience function to get a CTkImage for an emoji.
    
    Args:
        emoji: Single emoji character (e.g., "📋")
        size: Size in pixels (default: 18)
        
    Returns:
        CTkImage if available, None otherwise
    """
    renderer = get_emoji_renderer()
    return renderer.get_ctk_image(emoji, size)


def prepare_emoji_content(text: str, size: int = 18) -> Dict[str, Any]:
    """
    Convenience function to prepare CTkButton/CTkLabel content with emoji.
    
    Args:
        text: Text with optional leading emoji (e.g., "📋 Sessions")
        size: Emoji size in pixels (default: 18)
        
    Returns:
        Dict with "text", "image", and "compound" keys
        
    Usage:
        content = prepare_emoji_content("📋 Sessions")
        btn = CTkButton(parent, text=content["text"],
                       image=content["image"], compound=content["compound"])
    """
    renderer = get_emoji_renderer()
    return renderer.prepare_widget_content(text, size)