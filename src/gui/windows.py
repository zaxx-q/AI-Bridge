#!/usr/bin/env python3
"""
GUI window creation functions
"""

import threading

try:
    import dearpygui.dearpygui as dpg
    HAVE_GUI = True
except ImportError:
    HAVE_GUI = False
    dpg = None

from ..utils import strip_markdown
from ..session_manager import add_session, get_session, list_sessions, delete_session, save_sessions
from .core import (
    get_next_window_id, register_window, unregister_window,
    FONTS
)
from .utils import copy_to_clipboard, render_markdown


def create_result_window(text, endpoint=None, title=None):
    """Create a result display window"""
    if not HAVE_GUI:
        return
    
    window_id = get_next_window_id()
    window_tag = f"result_window_{window_id}"
    content_group_tag = f"result_content_{window_id}"
    status_tag = f"result_status_{window_id}"
    wrap_btn_tag = f"wrap_btn_{window_id}"
    mode_btn_tag = f"mode_btn_{window_id}"
    scroll_area_tag = f"scroll_area_{window_id}"
    
    title = title or f"Response - /{endpoint}" if endpoint else "AI Response"
    
    # State for toggles
    state = {
        'wrapped': True,
        'mode': 'rich',  # 'rich' (markdown) or 'text' (selectable)
        'original_text': text
    }
    
    def get_display_text():
        """Get text based on current display mode"""
        if state['mode'] == 'rich':
            return state['original_text']
        else:
            return strip_markdown(state['original_text'])
    
    def update_display():
        """Update the text display"""
        # Clear existing content
        dpg.delete_item(content_group_tag, children_only=True)
        
        # Update buttons
        dpg.configure_item(wrap_btn_tag, label=f"Wrap: {'ON' if state['wrapped'] else 'OFF'}")
        dpg.configure_item(mode_btn_tag, label=f"Mode: {'Rich' if state['mode'] == 'rich' else 'Text'}")
        
        # Configure parent scrollbar
        if state['wrapped']:
            dpg.configure_item(scroll_area_tag, horizontal_scrollbar=False)
        else:
            dpg.configure_item(scroll_area_tag, horizontal_scrollbar=True)
            
        # Add content based on mode
        if state['mode'] == 'text':
            # Use InputText for selection (monochrome)
            width = -1 if state['wrapped'] else 3000
            dpg.add_input_text(default_value=get_display_text(), parent=content_group_tag, 
                              multiline=True, readonly=True, width=width, height=-1)
        else:
            # Use Text for rich display (colored potential, clean wrapping)
            wrap_width = 0 if state['wrapped'] else -1
            render_markdown(state['original_text'], parent=content_group_tag, wrap_width=wrap_width, fonts=FONTS)
    
    def toggle_wrap():
        state['wrapped'] = not state['wrapped']
        update_display()
        dpg.set_value(status_tag, f"Wrap: {'ON' if state['wrapped'] else 'OFF'}")
    
    def toggle_mode():
        state['mode'] = 'text' if state['mode'] == 'rich' else 'rich'
        update_display()
        dpg.set_value(status_tag, f"Mode: {state['mode'].title()}")
    
    def copy_callback():
        if copy_to_clipboard(get_display_text()):
            dpg.set_value(status_tag, "✓ Copied to clipboard!")
        else:
            dpg.set_value(status_tag, "✗ Failed to copy")
    
    def close_callback():
        unregister_window(window_tag)
        dpg.delete_item(window_tag)
    
    register_window(window_tag)
    
    with dpg.window(label=title, tag=window_tag, width=700, height=500, 
                    pos=[100 + (window_id % 5) * 30, 100 + (window_id % 5) * 30],
                    on_close=close_callback):
        
        if endpoint:
            dpg.add_text(f"Endpoint: /{endpoint}")
            dpg.add_separator()
        
        # Toggle buttons row
        with dpg.group(horizontal=True):
            dpg.add_text("Response:", color=(150, 200, 255))
            dpg.add_spacer(width=20)
            dpg.add_button(label="Wrap: ON", tag=wrap_btn_tag, callback=toggle_wrap, width=100)
            dpg.add_button(label="Mode: Rich", tag=mode_btn_tag, callback=toggle_mode, width=100)
        
        # Scrollable area for text
        with dpg.child_window(tag=scroll_area_tag, border=False, width=-1, height=-60, horizontal_scrollbar=False):
            dpg.add_group(tag=content_group_tag)
            
        # Initial display
        update_display()
        
        dpg.add_separator()
        
        with dpg.group(horizontal=True):
            dpg.add_button(label="Copy to Clipboard", callback=copy_callback)
            dpg.add_button(label="Close", callback=close_callback)
            dpg.add_text("", tag=status_tag, color=(100, 255, 100))


def create_chat_window(session, initial_response=None):
    """Create a chat window for interactive conversation"""
    if not HAVE_GUI:
        return
    
    window_id = get_next_window_id()
    window_tag = f"chat_window_{window_id}"
    chat_log_group = f"chat_log_{window_id}"
    input_tag = f"chat_input_{window_id}"
    status_tag = f"chat_status_{window_id}"
    send_btn_tag = f"send_btn_{window_id}"
    wrap_btn_tag = f"wrap_btn_{window_id}"
    md_btn_tag = f"md_btn_{window_id}"
    select_btn_tag = f"select_btn_{window_id}"
    auto_scroll_btn_tag = f"auto_scroll_btn_{window_id}"
    scroll_area_tag = f"scroll_area_{window_id}"
    
    # State for toggles
    state = {
        'wrapped': True,
        'markdown': True,
        'selectable': False,
        'auto_scroll': True,
        'last_response': initial_response or ""
    }
    
    def get_conversation_text():
        """Build conversation text based on current display mode (for clipboard)"""
        parts = []
        for msg in session.messages:
            role = "You" if msg["role"] == "user" else "Assistant"
            content = msg['content']
            if not state['markdown']:
                content = strip_markdown(content)
            parts.append(f"[{role}]\n{content}\n")
        return "\n".join(parts)
    
    def update_chat_display(scroll_to_bottom=False):
        # Clear existing messages
        dpg.delete_item(chat_log_group, children_only=True)
        
        # Update buttons
        dpg.configure_item(wrap_btn_tag, label=f"Wrap: {'ON' if state['wrapped'] else 'OFF'}")
        dpg.configure_item(md_btn_tag, label=f"{'Markdown' if state['markdown'] else 'Plain Text'}")
        dpg.configure_item(select_btn_tag, label=f"Select: {'ON' if state['selectable'] else 'OFF'}")
        dpg.configure_item(auto_scroll_btn_tag, label="Autoscroll")
        
        # Handle wrapping
        wrap_width = 0 if state['wrapped'] else -1
        
        if state['wrapped']:
            dpg.configure_item(scroll_area_tag, horizontal_scrollbar=False)
        else:
            dpg.configure_item(scroll_area_tag, horizontal_scrollbar=True)
            
        if state['selectable']:
            # Selectable mode: One big text box (monochrome)
            width = -1 if state['wrapped'] else 3000
            dpg.add_input_text(default_value=get_conversation_text(), parent=chat_log_group, 
                              multiline=True, readonly=True, width=width, height=-1)
        else:
            # Rich mode: Colored text blocks
            for i, msg in enumerate(session.messages):
                role = msg["role"]
                content = msg["content"]
                if not state['markdown']:
                    content = strip_markdown(content)
                
                if role == "user":
                    dpg.add_text("You:", color=(100, 200, 255), parent=chat_log_group)
                else:
                    dpg.add_text("Assistant:", color=(150, 255, 150), parent=chat_log_group)
                
                if state['markdown']:
                    render_markdown(content, parent=chat_log_group, wrap_width=wrap_width, fonts=FONTS)
                else:
                    dpg.add_text(content, parent=chat_log_group, wrap=wrap_width, bullet=True)
                    
                dpg.add_separator(parent=chat_log_group)
        
        # Auto-scroll to bottom if enabled
        if scroll_to_bottom and state['auto_scroll']:
            dpg.set_y_scroll(scroll_area_tag, -1.0)
    
    def toggle_wrap():
        state['wrapped'] = not state['wrapped']
        update_chat_display()
        dpg.set_value(status_tag, f"Wrap: {'ON' if state['wrapped'] else 'OFF'}")
    
    def toggle_markdown():
        state['markdown'] = not state['markdown']
        update_chat_display()
        dpg.set_value(status_tag, f"Mode: {'Markdown' if state['markdown'] else 'Plain Text'}")
        
    def toggle_selectable():
        state['selectable'] = not state['selectable']
        update_chat_display()
        dpg.set_value(status_tag, f"Selectable: {'ON' if state['selectable'] else 'OFF'}")
    
    def toggle_auto_scroll():
        state['auto_scroll'] = not state['auto_scroll']
        dpg.set_value(status_tag, f"Autoscroll: {'ON' if state['auto_scroll'] else 'OFF'}")
    
    def send_callback(sender=None, app_data=None):
        user_input = dpg.get_value(input_tag).strip()
        if not user_input:
            dpg.set_value(status_tag, "Please enter a message")
            return
        
        # Disable input during processing
        dpg.configure_item(send_btn_tag, enabled=False)
        dpg.set_value(status_tag, "Sending...")
        
        def process_message():
            from ..api_client import call_api_chat
            from .. import web_server
            
            session.add_message("user", user_input)
            update_chat_display()
            dpg.set_value(input_tag, "")
            
            response_text, error = call_api_chat(
                session,
                web_server.CONFIG,
                web_server.AI_PARAMS,
                web_server.KEY_MANAGERS
            )
            
            if error:
                dpg.set_value(status_tag, f"Error: {error}")
                session.messages.pop()  # Remove failed user message
            else:
                session.add_message("assistant", response_text)
                state['last_response'] = response_text
                update_chat_display(scroll_to_bottom=True)
                dpg.set_value(status_tag, "✓ Response received")
                add_session(session, web_server.CONFIG.get("max_sessions", 50))
            
            dpg.configure_item(send_btn_tag, enabled=True)
        
        threading.Thread(target=process_message, daemon=True).start()
    
    def copy_all_callback():
        all_text = get_conversation_text()
        if copy_to_clipboard(all_text):
            dpg.set_value(status_tag, "✓ Copied all!")
        else:
            dpg.set_value(status_tag, "✗ Failed to copy")
    
    def copy_last_callback():
        text = state['last_response']
        if not state['markdown']:
            text = strip_markdown(text)
        if copy_to_clipboard(text):
            dpg.set_value(status_tag, "✓ Copied last response!")
        else:
            dpg.set_value(status_tag, "✗ Failed to copy")
    
    def close_callback():
        unregister_window(window_tag)
        dpg.delete_item(window_tag)
    
    register_window(window_tag)
    
    title = f"Chat - {session.title or session.session_id}"
    
    with dpg.window(label=title, tag=window_tag, width=750, height=600,
                    pos=[80 + (window_id % 5) * 30, 80 + (window_id % 5) * 30],
                    on_close=close_callback):
        
        dpg.add_text(f"Session: {session.session_id} | Endpoint: /{session.endpoint} | Provider: {session.provider}",
                    color=(150, 150, 200))
        dpg.add_separator()
        
        # Toggle buttons row
        with dpg.group(horizontal=True):
            dpg.add_text("Conversation:", color=(150, 200, 255))
            dpg.add_spacer(width=20)
            dpg.add_button(label="Wrap: ON", tag=wrap_btn_tag, callback=toggle_wrap, width=100)
            dpg.add_button(label="Markdown", tag=md_btn_tag, callback=toggle_markdown, width=100)
            dpg.add_button(label="Select: OFF", tag=select_btn_tag, callback=toggle_selectable, width=110)
            dpg.add_button(label="Autoscroll", tag=auto_scroll_btn_tag, callback=toggle_auto_scroll, width=130)
        
        # Scrollable area for chat log
        with dpg.child_window(tag=scroll_area_tag, border=False, width=-1, height=-150, horizontal_scrollbar=False):
            dpg.add_group(tag=chat_log_group)
            
        # Initial display
        update_chat_display()
        
        dpg.add_separator()
        dpg.add_text("Your message:", color=(150, 200, 255))
        
        # Key handler for Ctrl+Enter
        with dpg.handler_registry():
            dpg.add_key_release_handler(dpg.mvKey_Return, callback=lambda: send_callback() if (dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl)) else None)
        
        dpg.add_input_text(tag=input_tag, multiline=True, width=-1, height=60, 
                          hint="Type your follow-up message here... (Ctrl+Enter to send)")
        
        with dpg.group(horizontal=True):
            dpg.add_button(label="Send", tag=send_btn_tag, callback=send_callback)
            dpg.add_button(label="Copy All", callback=copy_all_callback)
            dpg.add_button(label="Copy Last", callback=copy_last_callback)
            dpg.add_button(label="Close", callback=close_callback)
        
        dpg.add_text("", tag=status_tag, color=(100, 255, 100))


def create_session_browser_window():
    """Create a session browser window"""
    if not HAVE_GUI:
        return
    
    window_id = get_next_window_id()
    window_tag = f"browser_window_{window_id}"
    table_tag = f"session_table_{window_id}"
    status_tag = f"browser_status_{window_id}"
    
    sessions = list_sessions()
    selected_session = {'id': None}
    
    def refresh_table():
        nonlocal sessions
        sessions = list_sessions()
        
        # Clear existing rows
        for child in dpg.get_item_children(table_tag, 1):
            dpg.delete_item(child)
        
        # Add rows
        for s in sessions:
            sid = s['id']
            with dpg.table_row(parent=table_tag):
                def make_callback(session_id):
                    return lambda *args: select_session(session_id)
                dpg.add_selectable(label=sid, callback=make_callback(sid))
                dpg.add_text(s['title'][:35] + ('...' if len(s['title']) > 35 else ''))
                dpg.add_text(s['endpoint'])
                dpg.add_text(s['provider'])
                dpg.add_text(str(s['messages']))
                updated = s['updated'][:16].replace('T', ' ') if s['updated'] else ''
                dpg.add_text(updated)
    
    def select_session(session_id):
        selected_session['id'] = session_id
        dpg.set_value(status_tag, f"Selected: {session_id}")
    
    def open_callback():
        if selected_session['id']:
            session = get_session(selected_session['id'])
            if session:
                create_chat_window(session)
                dpg.set_value(status_tag, f"Opened session {selected_session['id']}")
        else:
            dpg.set_value(status_tag, "No session selected")
    
    def delete_callback():
        if selected_session['id']:
            sid = selected_session['id']
            if delete_session(sid):
                save_sessions()
                selected_session['id'] = None
                refresh_table()
                dpg.set_value(status_tag, f"Deleted session {sid}")
        else:
            dpg.set_value(status_tag, "No session selected")
    
    def close_callback():
        unregister_window(window_tag)
        dpg.delete_item(window_tag)
    
    register_window(window_tag)
    
    with dpg.window(label="Session Browser", tag=window_tag, width=850, height=500,
                    pos=[50 + (window_id % 3) * 30, 50 + (window_id % 3) * 30],
                    on_close=close_callback):
        
        dpg.add_text("Saved Chat Sessions", color=(200, 200, 255))
        dpg.add_separator()
        
        with dpg.table(tag=table_tag, header_row=True, borders_innerH=True, 
                       borders_outerH=True, borders_innerV=True, borders_outerV=True,
                       scrollY=True, height=-60):
            
            dpg.add_table_column(label="ID", width_fixed=True, init_width_or_weight=70)
            dpg.add_table_column(label="Title", width_stretch=True)
            dpg.add_table_column(label="Endpoint", width_fixed=True, init_width_or_weight=80)
            dpg.add_table_column(label="Provider", width_fixed=True, init_width_or_weight=80)
            dpg.add_table_column(label="Msgs", width_fixed=True, init_width_or_weight=50)
            dpg.add_table_column(label="Updated", width_fixed=True, init_width_or_weight=130)
            
            for s in sessions:
                sid = s['id']
                with dpg.table_row():
                    def make_callback(session_id):
                        return lambda *args: select_session(session_id)
                    dpg.add_selectable(label=sid, callback=make_callback(sid))
                    dpg.add_text(s['title'][:35] + ('...' if len(s['title']) > 35 else ''))
                    dpg.add_text(s['endpoint'])
                    dpg.add_text(s['provider'])
                    dpg.add_text(str(s['messages']))
                    updated = s['updated'][:16].replace('T', ' ') if s['updated'] else ''
                    dpg.add_text(updated)
        
        dpg.add_separator()
        
        with dpg.group(horizontal=True):
            dpg.add_button(label="Open Chat", callback=open_callback)
            dpg.add_button(label="Delete", callback=delete_callback)
            dpg.add_button(label="Refresh", callback=refresh_table)
            dpg.add_button(label="Close", callback=close_callback)
        
        dpg.add_text("Click on a session ID to select it", tag=status_tag, color=(150, 150, 150))
