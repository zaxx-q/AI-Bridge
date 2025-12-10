#!/usr/bin/env python3
"""
GUI window creation functions - Tkinter implementation
"""

import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

from ..utils import strip_markdown
from ..session_manager import add_session, get_session, list_sessions, delete_session, save_sessions, ChatSession
from .core import get_next_window_id, register_window, unregister_window
from .utils import copy_to_clipboard, render_markdown, get_color_scheme, setup_text_tags


class ChatWindow:
    """Chat window for interactive conversation"""
    
    def __init__(self, session, initial_response: Optional[str] = None):
        self.session = session
        self.initial_response = initial_response
        
        self.window_id = get_next_window_id()
        self.window_tag = f"chat_window_{self.window_id}"
        
        # State
        self.wrapped = True
        self.markdown = True
        self.auto_scroll = True
        self.last_response = initial_response or ""
        self.is_loading = False
        
        # Streaming state
        self.streaming_text = ""
        self.streaming_thinking = ""
        self.is_streaming = False
        self.thinking_collapsed = True
        self.last_usage = None
        
        # Available models cache
        self.available_models = []
        # Get model from config rather than session
        from .. import web_server
        provider = web_server.CONFIG.get("default_provider", "google")
        self.selected_model = web_server.CONFIG.get(f"{provider}_model", "")
        
        # Colors
        self.colors = get_color_scheme()
        
        # Create window
        self._create_window()
    
    def _create_window(self):
        """Create the chat window"""
        if not GUI_ROOT:
            return
        
        self.root = tk.Toplevel(GUI_ROOT)
        self.root.title(f"Chat - {self.session.title or self.session.session_id}")
        self.root.geometry("750x600")
        self.root.configure(bg=self.colors["bg"])
        self.root.minsize(500, 400)
        
        # Position window
        offset = (self.window_id % 5) * 30
        self.root.geometry(f"+{80 + offset}+{80 + offset}")
        
        # Configure grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        
        # Session info (provider now comes from current config, not session)
        from .. import web_server
        current_provider = web_server.CONFIG.get("default_provider", "google")
        info_text = f"Session: {self.session.session_id} | Endpoint: /{self.session.endpoint} | Provider: {current_provider}"
        tk.Label(
            self.root,
            text=info_text,
            font=("Segoe UI", 9),
            bg=self.colors["bg"],
            fg=self.colors["blockquote"]
        ).grid(row=0, column=0, sticky=tk.W, padx=15, pady=(10, 5))
        
        # Toggle buttons row
        btn_frame = tk.Frame(self.root, bg=self.colors["bg"])
        btn_frame.grid(row=1, column=0, sticky=tk.EW, padx=15, pady=5)
        
        tk.Label(
            btn_frame,
            text="Conversation:",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["accent"]
        ).pack(side=tk.LEFT)
        
        tk.Label(btn_frame, width=2, bg=self.colors["bg"]).pack(side=tk.LEFT)
        
        self.wrap_btn = tk.Button(
            btn_frame,
            text="Wrap: ON",
            font=("Segoe UI", 9),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=8,
            command=self._toggle_wrap
        )
        self.wrap_btn.pack(side=tk.LEFT, padx=2)
        
        self.md_btn = tk.Button(
            btn_frame,
            text="Markdown",
            font=("Segoe UI", 9),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=8,
            command=self._toggle_markdown
        )
        self.md_btn.pack(side=tk.LEFT, padx=2)
        
        self.scroll_btn = tk.Button(
            btn_frame,
            text="Autoscroll: ON",
            font=("Segoe UI", 9),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=8,
            command=self._toggle_autoscroll
        )
        self.scroll_btn.pack(side=tk.LEFT, padx=2)
        
        # Model dropdown (on right side)
        tk.Label(btn_frame, width=3, bg=self.colors["bg"]).pack(side=tk.LEFT)
        tk.Label(
            btn_frame,
            text="Model:",
            font=("Segoe UI", 9),
            bg=self.colors["bg"],
            fg=self.colors["fg"]
        ).pack(side=tk.LEFT)
        
        self.model_var = tk.StringVar(value=self.selected_model or "(default)")
        self.model_dropdown = ttk.Combobox(
            btn_frame,
            textvariable=self.model_var,
            values=["(loading...)"],
            width=25,
            state="readonly"
        )
        self.model_dropdown.pack(side=tk.LEFT, padx=5)
        self.model_dropdown.bind("<<ComboboxSelected>>", self._on_model_select)
        
        # Load models in background
        threading.Thread(target=self._load_models, daemon=True).start()
        
        # Chat log area
        chat_frame = tk.Frame(self.root, bg=self.colors["bg"])
        chat_frame.grid(row=2, column=0, sticky=tk.NSEW, padx=15, pady=5)
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)
        
        self.chat_text = tk.Text(
            chat_frame,
            wrap=tk.WORD,
            font=("Segoe UI", 11),
            bg=self.colors["text_bg"],
            fg=self.colors["fg"],
            insertbackground=self.colors["fg"],
            relief=tk.FLAT,
            highlightbackground=self.colors["border"],
            highlightthickness=1,
            padx=10,
            pady=10
        )
        self.chat_text.grid(row=0, column=0, sticky=tk.NSEW)
        
        # Vertical scrollbar
        self.v_scrollbar = ttk.Scrollbar(chat_frame, orient=tk.VERTICAL, command=self.chat_text.yview)
        self.v_scrollbar.grid(row=0, column=1, sticky=tk.NS)
        self.chat_text.configure(yscrollcommand=self.v_scrollbar.set)
        
        # Horizontal scrollbar (shown when wrap is off)
        self.h_scrollbar = ttk.Scrollbar(chat_frame, orient=tk.HORIZONTAL, command=self.chat_text.xview)
        self.h_scrollbar.grid(row=1, column=0, sticky=tk.EW)
        self.h_scrollbar.grid_remove()  # Hide initially
        self.chat_text.configure(xscrollcommand=self.h_scrollbar.set)
        
        # Setup tags
        setup_text_tags(self.chat_text, self.colors)
        
        # Bind thinking header click to toggle expand/collapse
        self.chat_text.tag_bind("thinking_header", "<Button-1>", self._on_thinking_click)
        
        # Input section
        input_label = tk.Label(
            self.root,
            text="Your message:",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["accent"]
        )
        input_label.grid(row=3, column=0, sticky=tk.W, padx=15, pady=(10, 5))
        
        input_frame = tk.Frame(self.root, bg=self.colors["bg"])
        input_frame.grid(row=4, column=0, sticky=tk.EW, padx=15, pady=5)
        input_frame.columnconfigure(0, weight=1)
        
        self.input_text = tk.Text(
            input_frame,
            height=3,
            font=("Segoe UI", 11),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            insertbackground=self.colors["fg"],
            relief=tk.FLAT,
            highlightbackground=self.colors["border"],
            highlightthickness=1,
            padx=8,
            pady=8,
            wrap=tk.WORD
        )
        self.input_text.grid(row=0, column=0, sticky=tk.EW)
        self.input_text.insert("1.0", "Type your follow-up message here... (Ctrl+Enter to send)")
        self.input_text.configure(fg='gray')
        
        # Placeholder behavior
        def on_focus_in(event):
            if self.input_text.get("1.0", tk.END).strip() == "Type your follow-up message here... (Ctrl+Enter to send)":
                self.input_text.delete("1.0", tk.END)
                self.input_text.configure(fg=self.colors["fg"])
        
        def on_focus_out(event):
            if not self.input_text.get("1.0", tk.END).strip():
                self.input_text.insert("1.0", "Type your follow-up message here... (Ctrl+Enter to send)")
                self.input_text.configure(fg='gray')
        
        self.input_text.bind('<FocusIn>', on_focus_in)
        self.input_text.bind('<FocusOut>', on_focus_out)
        self.input_text.bind('<Control-Return>', lambda e: self._send())
        
        # Button row
        btn_row = tk.Frame(self.root, bg=self.colors["bg"])
        btn_row.grid(row=5, column=0, sticky=tk.EW, padx=15, pady=(5, 15))
        
        self.send_btn = tk.Button(
            btn_row,
            text="Send",
            font=("Segoe UI", 10),
            bg=self.colors["accent_green"],
            fg="#ffffff",
            activebackground="#45a049",
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._send
        )
        self.send_btn.pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_row,
            text="Copy All",
            font=("Segoe UI", 10),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._copy_all
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_row,
            text="Copy Last",
            font=("Segoe UI", 10),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._copy_last
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_row,
            text="Close",
            font=("Segoe UI", 10),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._close
        ).pack(side=tk.LEFT, padx=2)
        
        self.status_label = tk.Label(
            btn_row,
            text="",
            font=("Segoe UI", 10),
            bg=self.colors["bg"],
            fg=self.colors["accent_green"]
        )
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Register and bind
        register_window(self.window_tag)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        
        # Initial display
        self._update_chat_display()
    
    def _update_chat_display(self, scroll_to_bottom: bool = False, preserve_scroll: bool = False):
        """
        Update the chat display.
        
        Args:
            scroll_to_bottom: Scroll to bottom after update (for new messages)
            preserve_scroll: Preserve current scroll position (for toggle operations)
        """
        # Save scroll position before clearing
        saved_scroll = None
        if preserve_scroll:
            saved_scroll = self.chat_text.yview()
        
        self.chat_text.configure(state=tk.NORMAL)
        self.chat_text.delete("1.0", tk.END)
        
        # Update button labels
        self.wrap_btn.configure(text=f"Wrap: {'ON' if self.wrapped else 'OFF'}")
        self.md_btn.configure(text="Markdown" if self.markdown else "Raw Text")
        self.scroll_btn.configure(text=f"Autoscroll: {'ON' if self.auto_scroll else 'OFF'}")
        
        # Render messages
        for i, msg in enumerate(self.session.messages):
            role = msg["role"]
            content = msg["content"]
            thinking = msg.get("thinking", "")
            
            # Add spacing between messages
            if i > 0:
                self.chat_text.insert(tk.END, "\n")
            
            # Role label
            if role == "user":
                self.chat_text.insert(tk.END, "You:\n", "user_label")
            else:
                self.chat_text.insert(tk.END, "Assistant:\n", "assistant_label")
            
            # Thinking content (collapsible) - for assistant messages only
            if role == "assistant" and thinking:
                thinking_header = "▶ Thinking (click to expand)..." if self.thinking_collapsed else "▼ Thinking:"
                self.chat_text.insert(tk.END, f"{thinking_header}\n", "thinking_header")
                if not self.thinking_collapsed:
                    self.chat_text.insert(tk.END, thinking + "\n\n", "thinking_content")
            
            # Message content
            if self.markdown:
                role_for_bg = "user" if role == "user" else "assistant"
                render_markdown(content, self.chat_text, self.colors, 
                              wrap=self.wrapped, as_role=role_for_bg)
            else:
                # Plain text mode - no role-based styling, just normal text
                self.chat_text.configure(wrap=tk.WORD if self.wrapped else tk.NONE)
                self.chat_text.insert(tk.END, content, "normal")
            
            # Separator
            self.chat_text.insert(tk.END, "\n" + "─" * 50 + "\n", "separator")
        
        self.chat_text.configure(state=tk.DISABLED)
        
        # Handle scrolling
        if scroll_to_bottom and self.auto_scroll:
            self.chat_text.see(tk.END)
        elif preserve_scroll and saved_scroll:
            # Restore saved scroll position
            self.chat_text.yview_moveto(saved_scroll[0])
    
    def _toggle_wrap(self):
        self.wrapped = not self.wrapped
        # Show/hide horizontal scrollbar
        if self.wrapped:
            self.h_scrollbar.grid_remove()
        else:
            self.h_scrollbar.grid()
        self._update_chat_display(preserve_scroll=True)
        self.status_label.configure(text=f"Wrap: {'ON' if self.wrapped else 'OFF'}")
    
    def _toggle_markdown(self):
        self.markdown = not self.markdown
        self._update_chat_display(preserve_scroll=True)
        self.status_label.configure(text=f"Mode: {'Markdown' if self.markdown else 'Raw Text'}")
    
    def _toggle_autoscroll(self):
        self.auto_scroll = not self.auto_scroll
        self.scroll_btn.configure(text=f"Autoscroll: {'ON' if self.auto_scroll else 'OFF'}")
        self.status_label.configure(text=f"Autoscroll: {'ON' if self.auto_scroll else 'OFF'}")
    
    def _on_thinking_click(self, event):
        """Handle click on thinking header to toggle expand/collapse."""
        self.thinking_collapsed = not self.thinking_collapsed
        self._update_chat_display(preserve_scroll=True)
        state_text = "collapsed" if self.thinking_collapsed else "expanded"
        self.status_label.configure(text=f"Thinking: {state_text}")
    
    def _load_models(self):
        """Load available models in background"""
        try:
            from ..api_client import fetch_models
            from .. import web_server
            
            models, error = fetch_models(web_server.CONFIG, web_server.KEY_MANAGERS)
            
            if models and not error:
                self.available_models = models
                model_ids = [m['id'] for m in models]
                
                # Update dropdown on main thread
                def update_dropdown():
                    provider = web_server.CONFIG.get("default_provider", "google")
                    current = web_server.CONFIG.get(f"{provider}_model", "")
                    self.model_dropdown.configure(values=model_ids)
                    if current and current in model_ids:
                        self.model_var.set(current)
                    elif model_ids:
                        # Show current model or first available
                        self.model_var.set(current if current else model_ids[0])
                    else:
                        self.model_var.set("(no models)")
                
                self.root.after(0, update_dropdown)
        except Exception as e:
            print(f"[ChatWindow] Error loading models: {e}")
    
    def _on_model_select(self, event):
        """Handle model selection from dropdown"""
        from ..config import save_config_value
        from .. import web_server
        
        selected = self.model_var.get()
        if selected and selected not in ("(loading...)", "(no models)", "(default)"):
            self.selected_model = selected
            
            # Persist to config.ini for the current provider
            provider = web_server.CONFIG.get("default_provider", "google")
            config_key = f"{provider}_model"
            if save_config_value(config_key, selected):
                web_server.CONFIG[config_key] = selected
                self.status_label.configure(text=f"✓ Model: {selected}")
            else:
                self.status_label.configure(text=f"Model: {selected} (not saved)")
    
    def _send(self):
        """Send a message with streaming support"""
        if self.is_loading:
            return
        
        user_input = self.input_text.get("1.0", tk.END).strip()
        placeholder = "Type your follow-up message here... (Ctrl+Enter to send)"
        
        if not user_input or user_input == placeholder:
            self.status_label.configure(text="Please enter a message")
            return
        
        # Disable input
        self.is_loading = True
        self.send_btn.configure(state=tk.DISABLED)
        self.input_text.configure(state=tk.DISABLED)
        self.status_label.configure(text="Sending...")
        
        # Reset streaming state
        self.streaming_text = ""
        self.streaming_thinking = ""
        self.is_streaming = False
        self.last_usage = None
        
        def process_message():
            from .. import web_server
            from ..request_pipeline import RequestPipeline, RequestContext, RequestOrigin, StreamCallback
            
            self.session.add_message("user", user_input)
            
            # Update display and clear input on main thread
            self.root.after(0, lambda: self._update_chat_display(scroll_to_bottom=True))
            self.root.after(0, lambda: self.input_text.configure(state=tk.NORMAL))
            self.root.after(0, lambda: self.input_text.delete("1.0", tk.END))
            
            streaming_enabled = web_server.CONFIG.get("streaming_enabled", True)
            
            # Get current provider and model from config (not session)
            current_provider = web_server.CONFIG.get("default_provider", "google")
            current_model = self.selected_model or web_server.CONFIG.get(f"{current_provider}_model", "")
            
            # Setup context and callbacks
            ctx = RequestContext(
                origin=RequestOrigin.CHAT_WINDOW,
                provider=current_provider,
                model=current_model,
                streaming=streaming_enabled,
                thinking_enabled=web_server.CONFIG.get("thinking_enabled", False),
                session_id=str(self.session.session_id)
            )
            
            # Callbacks for UI updates
            def on_text(content):
                self.streaming_text += content
                self.root.after(0, lambda: self._update_streaming_display())
                
            def on_thinking(content):
                self.streaming_thinking += content
                self.root.after(0, lambda: self._update_streaming_display())
                
            def on_usage(content):
                self.last_usage = content
                
            def on_error(content):
                self.root.after(0, lambda: self.status_label.configure(
                    text=f"Error: {content}", fg=self.colors["accent_red"]
                ))
            
            callbacks = StreamCallback(
                on_text=on_text,
                on_thinking=on_thinking,
                on_usage=on_usage,
                on_error=on_error
            )
            
            # Execute request
            self.is_streaming = True
            self.root.after(0, lambda: self.status_label.configure(text="Streaming..." if streaming_enabled else "Processing..."))
            
            if streaming_enabled and current_provider in ("custom", "google", "openrouter"):
                ctx = RequestPipeline.execute_streaming(
                    ctx,
                    self.session,
                    web_server.CONFIG,
                    web_server.AI_PARAMS,
                    web_server.KEY_MANAGERS,
                    callbacks
                )
            else:
                self.is_streaming = False
                # For non-streaming, we construct messages manually
                messages = self.session.get_conversation_for_api(include_image=True)
                ctx = RequestPipeline.execute_simple(
                    ctx,
                    messages,
                    web_server.CONFIG,
                    web_server.AI_PARAMS,
                    web_server.KEY_MANAGERS
                )
                
            self.is_streaming = False
            self.last_usage = {
                "prompt_tokens": ctx.input_tokens,
                "completion_tokens": ctx.output_tokens,
                "total_tokens": ctx.total_tokens,
                "estimated": ctx.estimated
            }
            
            def handle_response():
                if ctx.error:
                    self.status_label.configure(text=f"Error: {ctx.error}", fg=self.colors["accent_red"])
                    self.session.messages.pop()  # Remove failed user message
                else:
                    # Store reasoning content alongside the message
                    msg_content = ctx.response_text
                    self.session.add_message("assistant", msg_content)
                    
                    # Store thinking if available (from streaming or potentially non-streaming if supported)
                    thinking_content = self.streaming_thinking or ctx.reasoning_text
                    if thinking_content:
                        if len(self.session.messages) > 0:
                            self.session.messages[-1]["thinking"] = thinking_content
                    
                    self.last_response = ctx.response_text
                    self._update_chat_display(scroll_to_bottom=True)
                    
                    # Show usage in status
                    usage_str = ""
                    if self.last_usage:
                        usage_str = f" | {self.last_usage.get('total_tokens', 0)} tokens"
                    
                    self.status_label.configure(
                        text=f"✓ Response received{usage_str}",
                        fg=self.colors["accent_green"]
                    )
                    add_session(self.session, web_server.CONFIG.get("max_sessions", 50))
                
                self.is_loading = False
                self.send_btn.configure(state=tk.NORMAL)
                self.input_text.configure(state=tk.NORMAL)
                
                # Reset streaming state
                self.streaming_text = ""
                self.streaming_thinking = ""
            
            self.root.after(0, handle_response)
        
        threading.Thread(target=process_message, daemon=True).start()
    
    def _update_streaming_display(self):
        """Update display during streaming - append new content"""
        if not self.is_streaming:
            return
        
        self.chat_text.configure(state=tk.NORMAL)
        
        # Find position after last separator
        try:
            last_sep_pos = self.chat_text.search("─" * 50, "end", backwards=True)
            if last_sep_pos:
                # Delete everything after the separator and add streaming content
                self.chat_text.delete(last_sep_pos, tk.END)
        except:
            pass
        
        # Add separator
        self.chat_text.insert(tk.END, "─" * 50 + "\n", "separator")
        
        # Add streaming assistant response
        self.chat_text.insert(tk.END, "\nAssistant:\n", "assistant_label")
        
        # Add thinking section if present (collapsible)
        if self.streaming_thinking:
            thinking_header = "▶ Thinking (click to expand)..." if self.thinking_collapsed else "▼ Thinking:"
            self.chat_text.insert(tk.END, f"{thinking_header}\n", "thinking_header")
            if not self.thinking_collapsed:
                self.chat_text.insert(tk.END, self.streaming_thinking + "\n", "thinking_content")
        
        # Add content
        if self.streaming_text:
            self.chat_text.insert(tk.END, self.streaming_text, "normal")
        else:
            self.chat_text.insert(tk.END, "...", "normal")
        
        self.chat_text.configure(state=tk.DISABLED)
        
        if self.auto_scroll:
            self.chat_text.see(tk.END)

    
    def _get_conversation_text(self) -> str:
        """Build conversation text for clipboard"""
        parts = []
        for msg in self.session.messages:
            role = "You" if msg["role"] == "user" else "Assistant"
            content = msg['content']
            if not self.markdown:
                content = strip_markdown(content)
            parts.append(f"[{role}]\n{content}\n")
        return "\n".join(parts)
    
    def _copy_all(self):
        text = self._get_conversation_text()
        if copy_to_clipboard(text, self.root):
            self.status_label.configure(text="✓ Copied all!", fg=self.colors["accent_green"])
        else:
            self.status_label.configure(text="✗ Failed to copy", fg=self.colors["accent_red"])
    
    def _copy_last(self):
        text = self.last_response
        if not self.markdown:
            text = strip_markdown(text)
        if copy_to_clipboard(text, self.root):
            self.status_label.configure(text="✓ Copied last response!", fg=self.colors["accent_green"])
        else:
            self.status_label.configure(text="✗ Failed to copy", fg=self.colors["accent_red"])
    
    def _close(self):
        unregister_window(self.window_tag)
        self.root.destroy()


class SessionBrowserWindow:
    """Session browser window for managing chat sessions"""
    
    def __init__(self):
        self.window_id = get_next_window_id()
        self.window_tag = f"browser_window_{self.window_id}"
        
        self.selected_session_id = None
        self.colors = get_color_scheme()
        
        # Sorting state
        self.sort_column = "Updated"
        self.sort_descending = True  # Default: newest first
        
        self._create_window()
    
    def _create_window(self):
        """Create the session browser window"""
        if not GUI_ROOT:
            return
        
        self.root = tk.Toplevel(GUI_ROOT)
        self.root.title("Session Browser")
        self.root.geometry("850x500")
        self.root.configure(bg=self.colors["bg"])
        self.root.minsize(600, 300)
        
        # Position window
        offset = (self.window_id % 3) * 30
        self.root.geometry(f"+{50 + offset}+{50 + offset}")
        
        # Configure grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        
        # Title
        tk.Label(
            self.root,
            text="Saved Chat Sessions",
            font=("Segoe UI", 14, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["accent"]
        ).grid(row=0, column=0, sticky=tk.W, padx=15, pady=(15, 10))
        
        # Treeview frame
        tree_frame = tk.Frame(self.root, bg=self.colors["bg"])
        tree_frame.grid(row=1, column=0, sticky=tk.NSEW, padx=15, pady=5)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        
        # Style configuration - must pass master to avoid conflicts with other Tk roots
        style = ttk.Style(master=self.root)
        style.theme_use('clam')
        
        # Configure treeview colors
        style.configure("Treeview",
            background=self.colors["text_bg"],
            foreground=self.colors["fg"],
            fieldbackground=self.colors["text_bg"],
            rowheight=28,
            font=("Segoe UI", 10)
        )
        style.configure("Treeview.Heading",
            background=self.colors["input_bg"],
            foreground=self.colors["fg"],
            font=("Segoe UI", 10, "bold")
        )
        style.map("Treeview",
            background=[("selected", self.colors["accent"])],
            foreground=[("selected", "#ffffff")]
        )
        
        # Create treeview (removed Provider column - sessions use current config)
        columns = ("ID", "Title", "Endpoint", "Messages", "Updated")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        
        # Configure columns with click-to-sort handlers
        for col in columns:
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_by_column(c))
        
        # Set column widths (redistributed after removing Provider)
        self.tree.column("ID", width=60, anchor=tk.W)
        self.tree.column("Title", width=320, anchor=tk.W)
        self.tree.column("Endpoint", width=90, anchor=tk.W)
        self.tree.column("Messages", width=60, anchor=tk.CENTER)
        self.tree.column("Updated", width=150, anchor=tk.W)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)
        
        # Bind selection
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self._open_session())
        
        # Button row
        btn_frame = tk.Frame(self.root, bg=self.colors["bg"])
        btn_frame.grid(row=2, column=0, sticky=tk.EW, padx=15, pady=(10, 15))
        
        tk.Button(
            btn_frame,
            text="New Session",
            font=("Segoe UI", 10),
            bg=self.colors["accent_green"],
            fg="#ffffff",
            activebackground="#45a049",
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._new_session
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_frame,
            text="Open Chat",
            font=("Segoe UI", 10),
            bg=self.colors["accent"],
            fg="#ffffff",
            activebackground=self.colors["accent_green"],
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._open_session
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_frame,
            text="Delete",
            font=("Segoe UI", 10),
            bg=self.colors["accent_red"],
            fg="#ffffff",
            activebackground="#c0392b",
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._delete_session
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_frame,
            text="Refresh",
            font=("Segoe UI", 10),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._refresh
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_frame,
            text="Close",
            font=("Segoe UI", 10),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._close
        ).pack(side=tk.LEFT, padx=2)
        
        self.status_label = tk.Label(
            btn_frame,
            text="Click on a session to select it",
            font=("Segoe UI", 10),
            bg=self.colors["bg"],
            fg=self.colors["blockquote"]
        )
        self.status_label.pack(side=tk.LEFT, padx=15)
        
        # Register and bind
        register_window(self.window_tag)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        
        # Load sessions
        self._refresh()
    
    def _sort_by_column(self, column):
        """Sort treeview by clicked column"""
        # Toggle direction if clicking same column
        if self.sort_column == column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column
            self.sort_descending = True  # New column defaults to descending
        
        self._refresh()
    
    def _refresh(self):
        """Refresh the session list"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        sessions = list_sessions()
        
        # Sort based on current settings
        reverse = self.sort_descending
        if self.sort_column == "ID":
            sessions.sort(key=lambda s: s['id'] if isinstance(s['id'], int) else 0, reverse=reverse)
        elif self.sort_column == "Title":
            sessions.sort(key=lambda s: (s['title'] or '').lower(), reverse=reverse)
        elif self.sort_column == "Endpoint":
            sessions.sort(key=lambda s: s['endpoint'], reverse=reverse)
        elif self.sort_column == "Messages":
            sessions.sort(key=lambda s: s['messages'], reverse=reverse)
        elif self.sort_column == "Updated":
            sessions.sort(key=lambda s: s['updated'] or '', reverse=reverse)
        
        # Update column headers to show sort indicator
        for col in ("ID", "Title", "Endpoint", "Messages", "Updated"):
            indicator = ""
            if col == self.sort_column:
                indicator = " ▼" if self.sort_descending else " ▲"
            self.tree.heading(col, text=col + indicator, command=lambda c=col: self._sort_by_column(c))
        
        for s in sessions:
            updated = s['updated'][:16].replace('T', ' ') if s['updated'] else ''
            title = s['title'][:35] + ('...' if len(s['title']) > 35 else '')
            
            self.tree.insert("", tk.END, iid=s['id'], values=(
                s['id'],
                title,
                s['endpoint'],
                s['messages'],
                updated
            ))
        
        self.status_label.configure(text=f"{len(sessions)} session(s) found")
    
    def _on_select(self, event):
        """Handle selection"""
        selection = self.tree.selection()
        if selection:
            self.selected_session_id = selection[0]
            self.status_label.configure(text=f"Selected: {self.selected_session_id}")
    
    def _new_session(self):
        """Create a new empty session and open it in a chat window"""
        session = ChatSession(endpoint="chat")
        add_session(session)
        ChatWindow(session)
        self._refresh()
        self.status_label.configure(text=f"Created new session {session.session_id}")
    
    def _open_session(self):
        """Open selected session in a chat window"""
        if not self.selected_session_id:
            self.status_label.configure(text="No session selected")
            return
        
        session = get_session(self.selected_session_id)
        if session:
            ChatWindow(session)
            self.status_label.configure(text=f"Opened session {self.selected_session_id}")
        else:
            self.status_label.configure(text="Session not found")
    
    def _delete_session(self):
        """Delete selected session"""
        if not self.selected_session_id:
            self.status_label.configure(text="No session selected")
            return
        
        sid = self.selected_session_id
        if delete_session(sid):
            save_sessions()
            self.selected_session_id = None
            self._refresh()
            self.status_label.configure(text=f"Deleted session {sid}")
        else:
            self.status_label.configure(text="Failed to delete session")
    
    def _close(self):
        unregister_window(self.window_tag)
        self.root.destroy()


# Factory functions for core.py
def create_chat_window(session, initial_response: Optional[str] = None):
    """Create a chat window for interactive conversation"""
    ChatWindow(session, initial_response)


def create_session_browser_window():
    """Create a session browser window"""
    SessionBrowserWindow()


class StandaloneChatWindow:
    """
    Standalone chat window that creates its own Tk root.
    Used when launching from non-GUI contexts.
    """
    
    def __init__(self, session, initial_response: Optional[str] = None):
        self.session = session
        self.initial_response = initial_response
        
        self.window_id = get_next_window_id()
        self.window_tag = f"standalone_chat_{self.window_id}"
        
        # State
        self.wrapped = True
        self.markdown = True
        self.auto_scroll = True
        self.last_response = initial_response or ""
        self.is_loading = False
        self._destroyed = False  # Track if window has been destroyed
        
        # Streaming state
        self.streaming_text = ""
        self.streaming_thinking = ""
        self.is_streaming = False
        self.thinking_collapsed = True
        self.last_usage = None
        
        # Available models cache
        self.available_models = []
        # Get model from config rather than session
        from .. import web_server
        provider = web_server.CONFIG.get("default_provider", "google")
        self.selected_model = web_server.CONFIG.get(f"{provider}_model", "")
        
        # Colors
        self.colors = get_color_scheme()
        
        self.root = None
    
    def _safe_after(self, delay: int, func):
        """
        Schedule a callback only if window still exists.
        Safe to call from background threads.
        """
        if self._destroyed:
            return
        try:
            if self.root and self.root.winfo_exists():
                self.root.after(delay, func)
        except (tk.TclError, RuntimeError):
            # Window was destroyed or Tk not in valid state
            pass
    
    def show(self):
        """Create and show the window with its own mainloop"""
        self.root = tk.Tk()
        self.root.title(f"Chat - {self.session.title or self.session.session_id}")
        self.root.geometry("750x600")
        self.root.configure(bg=self.colors["bg"])
        self.root.minsize(500, 400)
        
        # Position window
        offset = (self.window_id % 5) * 30
        self.root.geometry(f"+{80 + offset}+{80 + offset}")
        
        # Configure grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        
        # Session info (provider now comes from current config, not session)
        from .. import web_server
        current_provider = web_server.CONFIG.get("default_provider", "google")
        info_text = f"Session: {self.session.session_id} | Endpoint: /{self.session.endpoint} | Provider: {current_provider}"
        tk.Label(
            self.root,
            text=info_text,
            font=("Segoe UI", 9),
            bg=self.colors["bg"],
            fg=self.colors["blockquote"]
        ).grid(row=0, column=0, sticky=tk.W, padx=15, pady=(10, 5))
        
        # Toggle buttons row
        btn_frame = tk.Frame(self.root, bg=self.colors["bg"])
        btn_frame.grid(row=1, column=0, sticky=tk.EW, padx=15, pady=5)
        
        tk.Label(
            btn_frame,
            text="Conversation:",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["accent"]
        ).pack(side=tk.LEFT)
        
        tk.Label(btn_frame, width=2, bg=self.colors["bg"]).pack(side=tk.LEFT)
        
        self.wrap_btn = tk.Button(
            btn_frame,
            text="Wrap: ON",
            font=("Segoe UI", 9),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=8,
            command=self._toggle_wrap
        )
        self.wrap_btn.pack(side=tk.LEFT, padx=2)
        
        self.md_btn = tk.Button(
            btn_frame,
            text="Markdown",
            font=("Segoe UI", 9),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=8,
            command=self._toggle_markdown
        )
        self.md_btn.pack(side=tk.LEFT, padx=2)
        
        self.scroll_btn = tk.Button(
            btn_frame,
            text="Autoscroll: ON",
            font=("Segoe UI", 9),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=8,
            command=self._toggle_autoscroll
        )
        self.scroll_btn.pack(side=tk.LEFT, padx=2)
        
        # Model dropdown (on right side)
        tk.Label(btn_frame, width=3, bg=self.colors["bg"]).pack(side=tk.LEFT)
        tk.Label(
            btn_frame,
            text="Model:",
            font=("Segoe UI", 9),
            bg=self.colors["bg"],
            fg=self.colors["fg"]
        ).pack(side=tk.LEFT)
        
        self.model_var = tk.StringVar(value=self.selected_model or "(default)")
        self.model_dropdown = ttk.Combobox(
            btn_frame,
            textvariable=self.model_var,
            values=["(loading...)"],
            width=25,
            state="readonly"
        )
        self.model_dropdown.pack(side=tk.LEFT, padx=5)
        self.model_dropdown.bind("<<ComboboxSelected>>", self._on_model_select)
        
        # Load models in background
        threading.Thread(target=self._load_models, daemon=True).start()
        
        # Chat log area
        chat_frame = tk.Frame(self.root, bg=self.colors["bg"])
        chat_frame.grid(row=2, column=0, sticky=tk.NSEW, padx=15, pady=5)
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)
        
        self.chat_text = tk.Text(
            chat_frame,
            wrap=tk.WORD,
            font=("Segoe UI", 11),
            bg=self.colors["text_bg"],
            fg=self.colors["fg"],
            insertbackground=self.colors["fg"],
            relief=tk.FLAT,
            highlightbackground=self.colors["border"],
            highlightthickness=1,
            padx=10,
            pady=10
        )
        self.chat_text.grid(row=0, column=0, sticky=tk.NSEW)
        
        # Vertical scrollbar
        self.v_scrollbar = ttk.Scrollbar(chat_frame, orient=tk.VERTICAL, command=self.chat_text.yview)
        self.v_scrollbar.grid(row=0, column=1, sticky=tk.NS)
        self.chat_text.configure(yscrollcommand=self.v_scrollbar.set)
        
        # Horizontal scrollbar (shown when wrap is off)
        self.h_scrollbar = ttk.Scrollbar(chat_frame, orient=tk.HORIZONTAL, command=self.chat_text.xview)
        self.h_scrollbar.grid(row=1, column=0, sticky=tk.EW)
        self.h_scrollbar.grid_remove()  # Hide initially
        self.chat_text.configure(xscrollcommand=self.h_scrollbar.set)
        
        # Setup tags
        setup_text_tags(self.chat_text, self.colors)
        
        # Bind thinking header click to toggle expand/collapse
        self.chat_text.tag_bind("thinking_header", "<Button-1>", self._on_thinking_click)
        
        # Input section
        input_label = tk.Label(
            self.root,
            text="Your message:",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["accent"]
        )
        input_label.grid(row=3, column=0, sticky=tk.W, padx=15, pady=(10, 5))
        
        input_frame = tk.Frame(self.root, bg=self.colors["bg"])
        input_frame.grid(row=4, column=0, sticky=tk.EW, padx=15, pady=5)
        input_frame.columnconfigure(0, weight=1)
        
        self.input_text = tk.Text(
            input_frame,
            height=3,
            font=("Segoe UI", 11),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            insertbackground=self.colors["fg"],
            relief=tk.FLAT,
            highlightbackground=self.colors["border"],
            highlightthickness=1,
            padx=8,
            pady=8,
            wrap=tk.WORD
        )
        self.input_text.grid(row=0, column=0, sticky=tk.EW)
        self.input_text.insert("1.0", "Type your follow-up message here... (Ctrl+Enter to send)")
        self.input_text.configure(fg='gray')
        
        # Placeholder behavior
        def on_focus_in(event):
            if self.input_text.get("1.0", tk.END).strip() == "Type your follow-up message here... (Ctrl+Enter to send)":
                self.input_text.delete("1.0", tk.END)
                self.input_text.configure(fg=self.colors["fg"])
        
        def on_focus_out(event):
            if not self.input_text.get("1.0", tk.END).strip():
                self.input_text.insert("1.0", "Type your follow-up message here... (Ctrl+Enter to send)")
                self.input_text.configure(fg='gray')
        
        self.input_text.bind('<FocusIn>', on_focus_in)
        self.input_text.bind('<FocusOut>', on_focus_out)
        self.input_text.bind('<Control-Return>', lambda e: self._send())
        
        # Button row
        btn_row = tk.Frame(self.root, bg=self.colors["bg"])
        btn_row.grid(row=5, column=0, sticky=tk.EW, padx=15, pady=(5, 15))
        
        self.send_btn = tk.Button(
            btn_row,
            text="Send",
            font=("Segoe UI", 10),
            bg=self.colors["accent_green"],
            fg="#ffffff",
            activebackground="#45a049",
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._send
        )
        self.send_btn.pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_row,
            text="Copy All",
            font=("Segoe UI", 10),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._copy_all
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_row,
            text="Copy Last",
            font=("Segoe UI", 10),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._copy_last
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_row,
            text="Close",
            font=("Segoe UI", 10),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._close
        ).pack(side=tk.LEFT, padx=2)
        
        self.status_label = tk.Label(
            btn_row,
            text="",
            font=("Segoe UI", 10),
            bg=self.colors["bg"],
            fg=self.colors["accent_green"]
        )
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Register and bind
        register_window(self.window_tag)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        
        # Initial display
        self._update_chat_display()
        
        # Focus the window
        self.root.lift()
        self.root.focus_force()
        
        # Run mainloop
        self.root.mainloop()
    
    def _update_chat_display(self, scroll_to_bottom: bool = False, preserve_scroll: bool = False):
        """
        Update the chat display.
        
        Args:
            scroll_to_bottom: Scroll to bottom after update (for new messages)
            preserve_scroll: Preserve current scroll position (for toggle operations)
        """
        # Save scroll position before clearing
        saved_scroll = None
        if preserve_scroll:
            saved_scroll = self.chat_text.yview()
        
        self.chat_text.configure(state=tk.NORMAL)
        self.chat_text.delete("1.0", tk.END)
        
        # Update button labels
        self.wrap_btn.configure(text=f"Wrap: {'ON' if self.wrapped else 'OFF'}")
        self.md_btn.configure(text="Markdown" if self.markdown else "Raw Text")
        self.scroll_btn.configure(text=f"Autoscroll: {'ON' if self.auto_scroll else 'OFF'}")
        
        # Render messages
        for i, msg in enumerate(self.session.messages):
            role = msg["role"]
            content = msg["content"]
            thinking = msg.get("thinking", "")
            
            # Add spacing between messages
            if i > 0:
                self.chat_text.insert(tk.END, "\n")
            
            # Role label
            if role == "user":
                self.chat_text.insert(tk.END, "You:\n", "user_label")
            else:
                self.chat_text.insert(tk.END, "Assistant:\n", "assistant_label")
            
            # Thinking content (collapsible) - for assistant messages only
            if role == "assistant" and thinking:
                thinking_header = "▶ Thinking (click to expand)..." if self.thinking_collapsed else "▼ Thinking:"
                self.chat_text.insert(tk.END, f"{thinking_header}\n", "thinking_header")
                if not self.thinking_collapsed:
                    self.chat_text.insert(tk.END, thinking + "\n\n", "thinking_content")
            
            # Message content
            if self.markdown:
                role_for_bg = "user" if role == "user" else "assistant"
                render_markdown(content, self.chat_text, self.colors, 
                              wrap=self.wrapped, as_role=role_for_bg)
            else:
                # Raw text mode - show content as-is
                self.chat_text.configure(wrap=tk.WORD if self.wrapped else tk.NONE)
                self.chat_text.insert(tk.END, content, "normal")
            
            # Separator
            self.chat_text.insert(tk.END, "\n" + "─" * 50 + "\n", "separator")
        
        self.chat_text.configure(state=tk.DISABLED)
        
        # Handle scrolling
        if scroll_to_bottom and self.auto_scroll:
            self.chat_text.see(tk.END)
        elif preserve_scroll and saved_scroll:
            # Restore saved scroll position
            self.chat_text.yview_moveto(saved_scroll[0])
    
    def _toggle_wrap(self):
        self.wrapped = not self.wrapped
        if self.wrapped:
            self.h_scrollbar.grid_remove()
        else:
            self.h_scrollbar.grid()
        self._update_chat_display(preserve_scroll=True)
        self.status_label.configure(text=f"Wrap: {'ON' if self.wrapped else 'OFF'}")
    
    def _toggle_markdown(self):
        self.markdown = not self.markdown
        self._update_chat_display(preserve_scroll=True)
        self.status_label.configure(text=f"Mode: {'Markdown' if self.markdown else 'Raw Text'}")
    
    def _toggle_autoscroll(self):
        self.auto_scroll = not self.auto_scroll
        self.scroll_btn.configure(text=f"Autoscroll: {'ON' if self.auto_scroll else 'OFF'}")
        self.status_label.configure(text=f"Autoscroll: {'ON' if self.auto_scroll else 'OFF'}")
    
    def _on_thinking_click(self, event):
        """Handle click on thinking header to toggle expand/collapse."""
        self.thinking_collapsed = not self.thinking_collapsed
        self._update_chat_display(preserve_scroll=True)
        state_text = "collapsed" if self.thinking_collapsed else "expanded"
        self.status_label.configure(text=f"Thinking: {state_text}")
    
    def _load_models(self):
        """Load available models in background"""
        if self._destroyed:
            return
        try:
            from ..api_client import fetch_models
            from .. import web_server
            
            models, error = fetch_models(web_server.CONFIG, web_server.KEY_MANAGERS)
            
            if models and not error and not self._destroyed:
                self.available_models = models
                model_ids = [m['id'] for m in models]
                
                # Update dropdown on main thread (use safe_after)
                def update_dropdown():
                    if self._destroyed:
                        return
                    try:
                        provider = web_server.CONFIG.get("default_provider", "google")
                        current = web_server.CONFIG.get(f"{provider}_model", "")
                        self.model_dropdown.configure(values=model_ids)
                        if current and current in model_ids:
                            self.model_var.set(current)
                        elif model_ids:
                            self.model_var.set(current if current else model_ids[0])
                        else:
                            self.model_var.set("(no models)")
                    except tk.TclError:
                        pass  # Widget destroyed
                
                self._safe_after(0, update_dropdown)
        except Exception as e:
            print(f"[StandaloneChatWindow] Error loading models: {e}")
    
    def _on_model_select(self, event):
        """Handle model selection from dropdown"""
        from ..config import save_config_value
        from .. import web_server
        
        # Use dropdown.get() directly to avoid StringVar threading issues
        selected = self.model_dropdown.get()
        if selected and selected not in ("(loading...)", "(no models)", "(default)"):
            self.selected_model = selected
            
            # Persist to config.ini for the current provider
            provider = web_server.CONFIG.get("default_provider", "google")
            config_key = f"{provider}_model"
            if save_config_value(config_key, selected):
                web_server.CONFIG[config_key] = selected
                self.status_label.configure(text=f"✓ Model: {selected}")
            else:
                self.status_label.configure(text=f"Model: {selected} (not saved)")
    
    def _send(self):
        """Send a message with streaming support"""
        if self.is_loading:
            return
        
        user_input = self.input_text.get("1.0", tk.END).strip()
        placeholder = "Type your follow-up message here... (Ctrl+Enter to send)"
        
        if not user_input or user_input == placeholder:
            self.status_label.configure(text="Please enter a message")
            return
        
        # Disable input
        self.is_loading = True
        self.send_btn.configure(state=tk.DISABLED)
        self.input_text.configure(state=tk.DISABLED)
        self.status_label.configure(text="Sending...")
        
        # Reset streaming state
        self.streaming_text = ""
        self.streaming_thinking = ""
        self.is_streaming = False
        self.last_usage = None
        
        def process_message():
            from .. import web_server
            from ..request_pipeline import RequestPipeline, RequestContext, RequestOrigin, StreamCallback
            
            self.session.add_message("user", user_input)
            
            # Update display and clear input on main thread (use safe_after)
            self._safe_after(0, lambda: self._update_chat_display(scroll_to_bottom=True))
            self._safe_after(0, lambda: self.input_text.configure(state=tk.NORMAL))
            self._safe_after(0, lambda: self.input_text.delete("1.0", tk.END))
            
            streaming_enabled = web_server.CONFIG.get("streaming_enabled", True)
            
            # Get current provider and model from config (not session)
            current_provider = web_server.CONFIG.get("default_provider", "google")
            current_model = self.selected_model or web_server.CONFIG.get(f"{current_provider}_model", "")
            
            # Setup context and callbacks
            ctx = RequestContext(
                origin=RequestOrigin.CHAT_WINDOW,
                provider=current_provider,
                model=current_model,
                streaming=streaming_enabled,
                thinking_enabled=web_server.CONFIG.get("thinking_enabled", False),
                session_id=str(self.session.session_id)
            )
            
            # Callbacks for UI updates (use safe_after to handle window closure)
            def on_text(content):
                if self._destroyed:
                    return
                self.streaming_text += content
                self._safe_after(0, lambda: self._update_streaming_display())
                
            def on_thinking(content):
                if self._destroyed:
                    return
                self.streaming_thinking += content
                self._safe_after(0, lambda: self._update_streaming_display())
                
            def on_usage(content):
                self.last_usage = content
                
            def on_error(content):
                if self._destroyed:
                    return
                self._safe_after(0, lambda: self.status_label.configure(
                    text=f"Error: {content}", fg=self.colors["accent_red"]
                ))
            
            callbacks = StreamCallback(
                on_text=on_text,
                on_thinking=on_thinking,
                on_usage=on_usage,
                on_error=on_error
            )
            
            # Execute request
            self.is_streaming = True
            self._safe_after(0, lambda: self.status_label.configure(text="Streaming..." if streaming_enabled else "Processing..."))
            
            if streaming_enabled and current_provider in ("custom", "google", "openrouter"):
                ctx = RequestPipeline.execute_streaming(
                    ctx,
                    self.session,
                    web_server.CONFIG,
                    web_server.AI_PARAMS,
                    web_server.KEY_MANAGERS,
                    callbacks
                )
            else:
                self.is_streaming = False
                # For non-streaming, we construct messages manually
                messages = self.session.get_conversation_for_api(include_image=True)
                ctx = RequestPipeline.execute_simple(
                    ctx,
                    messages,
                    web_server.CONFIG,
                    web_server.AI_PARAMS,
                    web_server.KEY_MANAGERS
                )
            
            self.is_streaming = False
            self.last_usage = {
                "prompt_tokens": ctx.input_tokens,
                "completion_tokens": ctx.output_tokens,
                "total_tokens": ctx.total_tokens,
                "estimated": ctx.estimated
            }
            
            # Check if window was destroyed during request
            if self._destroyed:
                return
            
            def handle_response():
                if self._destroyed:
                    return
                    
                if ctx.error:
                    self.status_label.configure(text=f"Error: {ctx.error}", fg=self.colors["accent_red"])
                    self.session.messages.pop()  # Remove failed user message
                else:
                    # Store reasoning content alongside the message
                    msg_content = ctx.response_text
                    self.session.add_message("assistant", msg_content)
                    
                    # Store thinking if available (from streaming or potentially non-streaming if supported)
                    thinking_content = self.streaming_thinking or ctx.reasoning_text
                    if thinking_content:
                        if len(self.session.messages) > 0:
                            self.session.messages[-1]["thinking"] = thinking_content
                    
                    self.last_response = ctx.response_text
                    self._update_chat_display(scroll_to_bottom=True)
                    
                    # Show usage in status
                    usage_str = ""
                    if self.last_usage:
                        usage_str = f" | {self.last_usage.get('total_tokens', 0)} tokens"
                    
                    self.status_label.configure(
                        text=f"✓ Response received{usage_str}",
                        fg=self.colors["accent_green"]
                    )
                    add_session(self.session, web_server.CONFIG.get("max_sessions", 50))
                
                self.is_loading = False
                self.send_btn.configure(state=tk.NORMAL)
                self.input_text.configure(state=tk.NORMAL)
                
                # Reset streaming state
                self.streaming_text = ""
                self.streaming_thinking = ""
            
            self._safe_after(0, handle_response)
        
        threading.Thread(target=process_message, daemon=True).start()
    
    def _update_streaming_display(self):
        """Update display during streaming"""
        if not self.is_streaming or self._destroyed:
            return
        
        self.chat_text.configure(state=tk.NORMAL)
        
        # Find and remove streaming content after last separator
        try:
            last_sep_pos = self.chat_text.search("─" * 50, "end", backwards=True)
            if last_sep_pos:
                self.chat_text.delete(last_sep_pos, tk.END)
        except:
            pass
        
        # Add separator
        self.chat_text.insert(tk.END, "─" * 50 + "\n", "separator")
        
        # Add streaming assistant response
        self.chat_text.insert(tk.END, "\nAssistant:\n", "assistant_label")
        
        # Add thinking section if present
        if self.streaming_thinking:
            thinking_header = "▶ Thinking..." if self.thinking_collapsed else "▼ Thinking:"
            self.chat_text.insert(tk.END, f"{thinking_header}\n", "thinking_header")
            if not self.thinking_collapsed:
                self.chat_text.insert(tk.END, self.streaming_thinking + "\n", "thinking_content")
        
        # Add content
        if self.streaming_text:
            self.chat_text.insert(tk.END, self.streaming_text, "normal")
        else:
            self.chat_text.insert(tk.END, "...", "normal")
        
        self.chat_text.configure(state=tk.DISABLED)
        
        if self.auto_scroll:
            self.chat_text.see(tk.END)

    
    def _get_conversation_text(self) -> str:
        """Build conversation text for clipboard"""
        parts = []
        for msg in self.session.messages:
            role = "You" if msg["role"] == "user" else "Assistant"
            parts.append(f"[{role}]\n{msg['content']}\n")
        return "\n".join(parts)
    
    def _copy_all(self):
        text = self._get_conversation_text()
        if copy_to_clipboard(text, self.root):
            self.status_label.configure(text="✓ Copied all!", fg=self.colors["accent_green"])
        else:
            self.status_label.configure(text="✗ Failed to copy", fg=self.colors["accent_red"])
    
    def _copy_last(self):
        text = self.last_response
        if copy_to_clipboard(text, self.root):
            self.status_label.configure(text="✓ Copied last response!", fg=self.colors["accent_green"])
        else:
            self.status_label.configure(text="✗ Failed to copy", fg=self.colors["accent_red"])
    
    def _close(self):
        """Close window and cleanup resources"""
        self._destroyed = True
        self.is_streaming = False
        unregister_window(self.window_tag)
        try:
            if self.root:
                self.root.destroy()
        except tk.TclError:
            pass
        self.root = None


class StandaloneSessionBrowserWindow:
    """
    Standalone session browser window that creates its own Tk root.
    Used when launching from non-GUI contexts.
    """
    
    def __init__(self):
        self.window_id = get_next_window_id()
        self.window_tag = f"standalone_browser_{self.window_id}"
        
        self.selected_session_id = None
        self.colors = get_color_scheme()
        
        # Sorting state
        self.sort_column = "Updated"
        self.sort_descending = True  # Default: newest first
        
        self.root = None
        self._destroyed = False
    
    def _safe_after(self, delay: int, func):
        """Schedule a callback only if window still exists."""
        if self._destroyed:
            return
        try:
            if self.root and self.root.winfo_exists():
                self.root.after(delay, func)
        except (tk.TclError, RuntimeError):
            pass
    
    def show(self):
        """Create and show the window with its own mainloop"""
        self.root = tk.Tk()
        self.root.title("Session Browser")
        self.root.geometry("850x500")
        self.root.configure(bg=self.colors["bg"])
        self.root.minsize(600, 300)
        
        # Position window
        offset = (self.window_id % 3) * 30
        self.root.geometry(f"+{50 + offset}+{50 + offset}")
        
        # Configure grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        
        # Title
        tk.Label(
            self.root,
            text="Saved Chat Sessions",
            font=("Segoe UI", 14, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["accent"]
        ).grid(row=0, column=0, sticky=tk.W, padx=15, pady=(15, 10))
        
        # Treeview frame
        tree_frame = tk.Frame(self.root, bg=self.colors["bg"])
        tree_frame.grid(row=1, column=0, sticky=tk.NSEW, padx=15, pady=5)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        
        # Style configuration - must pass master to avoid conflicts with other Tk roots
        style = ttk.Style(master=self.root)
        style.theme_use('clam')
        
        # Configure treeview colors
        style.configure("Treeview",
            background=self.colors["text_bg"],
            foreground=self.colors["fg"],
            fieldbackground=self.colors["text_bg"],
            rowheight=28,
            font=("Segoe UI", 10)
        )
        style.configure("Treeview.Heading",
            background=self.colors["input_bg"],
            foreground=self.colors["fg"],
            font=("Segoe UI", 10, "bold")
        )
        style.map("Treeview",
            background=[("selected", self.colors["accent"])],
            foreground=[("selected", "#ffffff")]
        )
        
        # Create treeview (removed Provider column - sessions use current config)
        columns = ("ID", "Title", "Endpoint", "Messages", "Updated")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        
        # Configure columns with click-to-sort handlers
        for col in columns:
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_by_column(c))
        
        # Set column widths (redistributed after removing Provider)
        self.tree.column("ID", width=60, anchor=tk.W)
        self.tree.column("Title", width=320, anchor=tk.W)
        self.tree.column("Endpoint", width=90, anchor=tk.W)
        self.tree.column("Messages", width=60, anchor=tk.CENTER)
        self.tree.column("Updated", width=150, anchor=tk.W)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)
        
        # Bind selection
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self._open_session())
        
        # Button row
        btn_frame = tk.Frame(self.root, bg=self.colors["bg"])
        btn_frame.grid(row=2, column=0, sticky=tk.EW, padx=15, pady=(10, 15))
        
        tk.Button(
            btn_frame,
            text="New Session",
            font=("Segoe UI", 10),
            bg=self.colors["accent_green"],
            fg="#ffffff",
            activebackground="#45a049",
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._new_session
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_frame,
            text="Open Chat",
            font=("Segoe UI", 10),
            bg=self.colors["accent"],
            fg="#ffffff",
            activebackground=self.colors["accent_green"],
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._open_session
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_frame,
            text="Delete",
            font=("Segoe UI", 10),
            bg=self.colors["accent_red"],
            fg="#ffffff",
            activebackground="#c0392b",
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._delete_session
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_frame,
            text="Refresh",
            font=("Segoe UI", 10),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._refresh
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_frame,
            text="Close",
            font=("Segoe UI", 10),
            bg=self.colors["input_bg"],
            fg=self.colors["fg"],
            activebackground=self.colors["border"],
            relief=tk.FLAT,
            padx=15,
            pady=5,
            command=self._close
        ).pack(side=tk.LEFT, padx=2)
        
        self.status_label = tk.Label(
            btn_frame,
            text="Click on a session to select it",
            font=("Segoe UI", 10),
            bg=self.colors["bg"],
            fg=self.colors["blockquote"]
        )
        self.status_label.pack(side=tk.LEFT, padx=15)
        
        # Register and bind
        register_window(self.window_tag)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        
        # Load sessions
        self._refresh()
        
        # Focus the window
        self.root.lift()
        self.root.focus_force()
        
        # Run mainloop
        self.root.mainloop()
    
    def _sort_by_column(self, column):
        """Sort treeview by clicked column"""
        # Toggle direction if clicking same column
        if self.sort_column == column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column
            self.sort_descending = True  # New column defaults to descending
        
        self._refresh()
    
    def _refresh(self):
        """Refresh the session list"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        sessions = list_sessions()
        
        # Sort based on current settings
        reverse = self.sort_descending
        if self.sort_column == "ID":
            sessions.sort(key=lambda s: s['id'] if isinstance(s['id'], int) else 0, reverse=reverse)
        elif self.sort_column == "Title":
            sessions.sort(key=lambda s: (s['title'] or '').lower(), reverse=reverse)
        elif self.sort_column == "Endpoint":
            sessions.sort(key=lambda s: s['endpoint'], reverse=reverse)
        elif self.sort_column == "Messages":
            sessions.sort(key=lambda s: s['messages'], reverse=reverse)
        elif self.sort_column == "Updated":
            sessions.sort(key=lambda s: s['updated'] or '', reverse=reverse)
        
        # Update column headers to show sort indicator
        for col in ("ID", "Title", "Endpoint", "Messages", "Updated"):
            indicator = ""
            if col == self.sort_column:
                indicator = " ▼" if self.sort_descending else " ▲"
            self.tree.heading(col, text=col + indicator, command=lambda c=col: self._sort_by_column(c))
        
        for s in sessions:
            updated = s['updated'][:16].replace('T', ' ') if s['updated'] else ''
            title = s['title'][:35] + ('...' if len(s['title']) > 35 else '')
            
            self.tree.insert("", tk.END, iid=s['id'], values=(
                s['id'],
                title,
                s['endpoint'],
                s['messages'],
                updated
            ))
        
        self.status_label.configure(text=f"{len(sessions)} session(s) found")
    
    def _on_select(self, event):
        """Handle selection"""
        selection = self.tree.selection()
        if selection:
            self.selected_session_id = selection[0]
            self.status_label.configure(text=f"Selected: {self.selected_session_id}")
    
    def _new_session(self):
        """Create a new empty session and open it in a chat window"""
        session = ChatSession(endpoint="chat")
        add_session(session)
        
        # Open in a new thread with its own Tk root
        def open_chat():
            chat = StandaloneChatWindow(session)
            chat.show()
        threading.Thread(target=open_chat, daemon=True).start()
        
        self._refresh()
        self.status_label.configure(text=f"Created new session {session.session_id}")
    
    def _open_session(self):
        """Open selected session in a chat window"""
        if not self.selected_session_id:
            self.status_label.configure(text="No session selected")
            return
        
        session = get_session(self.selected_session_id)
        if session:
            # Open in a new thread with its own Tk root
            def open_chat():
                chat = StandaloneChatWindow(session)
                chat.show()
            threading.Thread(target=open_chat, daemon=True).start()
            self.status_label.configure(text=f"Opened session {self.selected_session_id}")
        else:
            self.status_label.configure(text="Session not found")
    
    def _delete_session(self):
        """Delete selected session"""
        if not self.selected_session_id:
            self.status_label.configure(text="No session selected")
            return
        
        sid = self.selected_session_id
        if delete_session(sid):
            save_sessions()
            self.selected_session_id = None
            self._refresh()
            self.status_label.configure(text=f"Deleted session {sid}")
        else:
            self.status_label.configure(text="Failed to delete session")
    
    def _close(self):
        """Close window and cleanup resources"""
        self._destroyed = True
        unregister_window(self.window_tag)
        try:
            if self.root:
                self.root.destroy()
        except tk.TclError:
            pass
        self.root = None
