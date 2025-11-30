#!/usr/bin/env python3
"""
GUI utility functions for clipboard and markdown rendering
"""

import re
import sys

try:
    import dearpygui.dearpygui as dpg
    HAVE_GUI = True
except ImportError:
    HAVE_GUI = False
    dpg = None


def copy_to_clipboard(text):
    """Cross-platform clipboard copy"""
    try:
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


def render_markdown(text, parent, wrap_width=-1, fonts=None):
    """Render markdown text to DPG items"""
    if not HAVE_GUI:
        return
    
    fonts = fonts or {}
    lines = text.split('\n')
    in_code_block = False
    code_block_lines = []
    code_lang = ""
    
    # Helper to flush code block
    def flush_code_block():
        nonlocal code_block_lines, code_lang
        if code_block_lines:
            code_text = '\n'.join(code_block_lines)
            # Estimate height: lines * 18 pixels + padding
            height = max(60, len(code_block_lines) * 18 + 20)
            dpg.add_input_text(default_value=code_text, multiline=True, readonly=True, 
                              width=-1, height=height, parent=parent)
            code_block_lines = []
            code_lang = ""

    for line in lines:
        stripped_line = line.strip()
        
        # Code Block Detection
        if stripped_line.startswith('```'):
            if in_code_block:
                # End of code block
                flush_code_block()
                in_code_block = False
            else:
                # Start of code block
                in_code_block = True
                code_lang = stripped_line[3:].strip()
            continue
            
        if in_code_block:
            code_block_lines.append(line)
            continue
            
        # Headers
        if stripped_line.startswith('#'):
            level = len(stripped_line.split(' ')[0])
            content = stripped_line.lstrip('#').strip()
            if level == 1:
                item = dpg.add_text(content, parent=parent, wrap=wrap_width, color=(255, 200, 100))
                if fonts.get("header1"): dpg.bind_item_font(item, fonts.get("header1"))
            elif level == 2:
                item = dpg.add_text(content, parent=parent, wrap=wrap_width, color=(200, 200, 255))
                if fonts.get("header2"): dpg.bind_item_font(item, fonts.get("header2"))
            else:
                item = dpg.add_text(content, parent=parent, wrap=wrap_width, color=(180, 220, 255))
                if fonts.get("bold"): dpg.bind_item_font(item, fonts.get("bold"))
            continue
            
        # Bullet Points
        if stripped_line.startswith('- ') or stripped_line.startswith('* '):
            content = stripped_line[2:].strip()
            
            # Check if entire content is bold: **text**
            bold_match = re.match(r'^\*\*(.+?)\*\*$', content)
            if bold_match:
                # Entire bullet content is bold
                text_content = bold_match.group(1)
                item = dpg.add_text(text_content, parent=parent, wrap=wrap_width, bullet=True)
                if fonts.get("bold"):
                    dpg.bind_item_font(item, fonts.get("bold"))
            else:
                # Mixed or no formatting - strip markers for cleaner display
                clean_content = content.replace('**', '').replace('__', '')
                dpg.add_text(clean_content, parent=parent, wrap=wrap_width, bullet=True)
            continue
            
        # Bold text (whole line or with trailing punctuation)
        # Match **text** or **text**. or **text**, etc.
        bold_match = re.match(r'^\*\*(.+?)\*\*([.,;:!?\s]*)$', stripped_line)
        if bold_match:
            text_content = bold_match.group(1)
            punctuation = bold_match.group(2)
            full_content = text_content + punctuation
            item = dpg.add_text(full_content, parent=parent, wrap=wrap_width)
            if fonts.get("bold"):
                dpg.bind_item_font(item, fonts.get("bold"))
            continue
            
        # Italic text (whole line or with trailing punctuation)
        italic_match = re.match(r'^[\*_](.+?)[\*_]([.,;:!?\s]*)$', stripped_line)
        if italic_match and len(stripped_line) > 2:
            text_content = italic_match.group(1)
            punctuation = italic_match.group(2)
            full_content = text_content + punctuation
            item = dpg.add_text(full_content, parent=parent, wrap=wrap_width)
            if fonts.get("italic"):
                dpg.bind_item_font(item, fonts.get("italic"))
            continue

        # Check if empty line (spacer)
        if not stripped_line:
            dpg.add_spacer(height=5, parent=parent)
            continue
            
        dpg.add_text(line, parent=parent, wrap=wrap_width)

    # Flush any remaining code block
    if in_code_block:
        flush_code_block()
