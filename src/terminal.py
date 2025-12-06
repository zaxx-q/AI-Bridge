#!/usr/bin/env python3
"""
Terminal interactive session manager
"""

import sys
import time

from .session_manager import (
    list_sessions, get_session, delete_session, save_sessions,
    CHAT_SESSIONS, SESSION_LOCK, clear_all_sessions
)
from .gui.core import show_session_browser, get_gui_status, HAVE_GUI


def terminal_session_manager():
    """Interactive terminal session manager"""
    print("\n" + "─"*60)
    print("TERMINAL COMMANDS (press key anytime):")
    print("  [L] List sessions       [O] Open session browser (GUI)")
    print("  [S] Show session        [D] Delete session")
    print("  [C] Clear all sessions  [H] Help")
    print("  [G] Toggle GUI status   [M] Manage models")
    print("  [T] Toggle thinking     [R] Toggle streaming")
    print("─"*60 + "\n")
    
    def get_input_nonblocking():
        """Get keyboard input without blocking"""
        if sys.platform == 'win32':
            import msvcrt
            if msvcrt.kbhit():
                return msvcrt.getch().decode('utf-8', errors='ignore').lower()
            return None
        else:
            import select
            import tty
            import termios
            old_settings = None
            try:
                old_settings = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    return sys.stdin.read(1).lower()
            except:
                pass
            finally:
                if old_settings:
                    try:
                        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                    except:
                        pass
            return None
    
    while True:
        try:
            key = get_input_nonblocking()
            
            if key == 'l':
                sessions = list_sessions()
                print(f"\n{'─'*60}")
                print(f"SAVED SESSIONS ({len(sessions)} total):")
                print(f"{'─'*60}")
                if not sessions:
                    print("  (No sessions)")
                else:
                    for i, s in enumerate(sessions[:10]):
                        print(f"  [{s['id']}] {s['title'][:40]} ({s['messages']} msgs, {s['provider']})")
                    if len(sessions) > 10:
                        print(f"  ... and {len(sessions) - 10} more")
                print(f"{'─'*60}\n")
            
            elif key == 'o':
                if HAVE_GUI:
                    print("\n[Opening session browser...]\n")
                    show_session_browser()
                else:
                    print("\n[GUI not available]\n")
            
            elif key == 'g':
                status = get_gui_status()
                print(f"\n{'─'*60}")
                print(f"GUI STATUS:")
                print(f"  Available: {status['available']}")
                print(f"  Running: {status['running']}")
                print(f"  Context Created: {status['context_created']}")
                print(f"  Open Windows: {status['open_windows']}")
                print(f"{'─'*60}\n")
            
            elif key == 'm':
                # Model management
                from . import web_server
                from .api_client import fetch_models
                from .config import save_config_value
                
                print(f"\n{'─'*60}")
                print("MODEL MANAGEMENT")
                print(f"{'─'*60}")
                provider = web_server.CONFIG.get("default_provider", "custom")
                current_model = web_server.CONFIG.get(f"{provider}_model", "not set")
                print(f"  Provider: {provider}")
                print(f"  Current model: {current_model}")
                print(f"\n  Fetching available models...")
                
                models, error = fetch_models(web_server.CONFIG, web_server.KEY_MANAGERS)
                if error:
                    print(f"  [Error] {error}")
                elif models:
                    print(f"\n  Available models ({len(models)}):")
                    for i, m in enumerate(models):
                        print(f"    [{i+1}] {m['id']}")
                    
                    print("\n  Enter model number or full name (or 'q' to cancel): ", end='', flush=True)
                    try:
                        choice = input().strip()
                        if choice.lower() != 'q':
                            # Try to parse as number
                            try:
                                idx = int(choice) - 1
                                if 0 <= idx < len(models):
                                    new_model = models[idx]['id']
                                else:
                                    new_model = choice
                            except ValueError:
                                new_model = choice
                            
                            # Update config
                            config_key = f"{provider}_model"
                            if save_config_value(config_key, new_model):
                                web_server.CONFIG[config_key] = new_model
                                print(f"  ✓ Model set to: {new_model}")
                            else:
                                print(f"  ✗ Failed to save to config")
                    except:
                        pass
                else:
                    print("  No models available")
                print(f"{'─'*60}\n")
            
            elif key == 't':
                # Toggle thinking mode
                from . import web_server
                from .config import save_config_value
                
                current = web_server.CONFIG.get("thinking_enabled", False)
                new_value = not current
                
                if save_config_value("thinking_enabled", new_value):
                    web_server.CONFIG["thinking_enabled"] = new_value
                    print(f"\n✓ Thinking mode: {'ENABLED' if new_value else 'DISABLED'}")
                    
                    # Also show current output mode
                    output_mode = web_server.CONFIG.get("thinking_output", "reasoning_content")
                    print(f"  Output mode: {output_mode}")
                else:
                    print("\n✗ Failed to toggle thinking mode")
                print()
            
            elif key == 'r':
                # Toggle streaming mode
                from . import web_server
                from .config import save_config_value
                
                current = web_server.CONFIG.get("streaming_enabled", True)
                new_value = not current
                
                if save_config_value("streaming_enabled", new_value):
                    web_server.CONFIG["streaming_enabled"] = new_value
                    print(f"\n✓ Streaming: {'ENABLED' if new_value else 'DISABLED'}\n")
                else:
                    print("\n✗ Failed to toggle streaming mode\n")
            
            elif key == 's':
                print("\nEnter session ID: ", end='', flush=True)
                try:
                    session_id = input().strip()
                    session = get_session(session_id)
                    if session:
                        print(f"\n{'─'*60}")
                        print(f"SESSION: {session.session_id}")
                        print(f"Title: {session.title}")
                        print(f"Endpoint: {session.endpoint} | Provider: {session.provider}")
                        print(f"Created: {session.created_at}")
                        print(f"{'─'*60}")
                        for msg in session.messages:
                            role = "USER" if msg["role"] == "user" else "ASSISTANT"
                            print(f"\n[{role}]")
                            print(msg['content'][:500] + ('...' if len(msg['content']) > 500 else ''))
                        print(f"{'─'*60}\n")
                        
                        if HAVE_GUI:
                            open_gui = input("Open in chat GUI? [y/N]: ").strip().lower()
                            if open_gui == 'y':
                                from .gui.core import show_chat_gui
                                show_chat_gui(session)
                    else:
                        print(f"Session '{session_id}' not found.\n")
                except:
                    pass
            
            elif key == 'd':
                print("\nEnter session ID to delete: ", end='', flush=True)
                try:
                    session_id = input().strip()
                    if get_session(session_id):
                        confirm = input(f"Delete session {session_id}? [y/N]: ").strip().lower()
                        if confirm == 'y':
                            if delete_session(session_id):
                                save_sessions()
                                print(f"Session {session_id} deleted.\n")
                    else:
                        print(f"Session '{session_id}' not found.\n")
                except:
                    pass
            
            elif key == 'c':
                try:
                    confirm = input("\nClear ALL sessions? This cannot be undone. [y/N]: ").strip().lower()
                    if confirm == 'y':
                        clear_all_sessions()
                        save_sessions()
                        print("All sessions cleared.\n")
                except:
                    pass
            
            elif key == 'h':
                print("\n" + "─"*60)
                print("TERMINAL COMMANDS:")
                print("  [L] List sessions       - Show recent saved sessions")
                print("  [O] Open browser        - Open session browser GUI")
                print("  [S] Show session        - Display a session by ID")
                print("  [D] Delete session      - Delete a session by ID")
                print("  [C] Clear all           - Delete all sessions")
                print("  [G] GUI status          - Show GUI state information")
                print("  [M] Manage models       - List/set models from API")
                print("  [T] Toggle thinking     - Enable/disable thinking mode")
                print("  [R] Toggle streaming    - Enable/disable streaming")
                print("  [H] Help                - Show this help")
                print("─"*60 + "\n")
            
            time.sleep(0.1)
        
        except Exception as e:
            print(f"[Terminal Error] {e}")
            time.sleep(1)


def print_usage(usage_data, prefix=""):
    """Print token usage information to console"""
    if not usage_data:
        return
    
    input_tokens = usage_data.get("prompt_tokens", 0)
    output_tokens = usage_data.get("completion_tokens", 0)
    total_tokens = usage_data.get("total_tokens", input_tokens + output_tokens)
    estimated = usage_data.get("estimated", False)
    
    est_mark = " (est)" if estimated else ""
    print(f"{prefix}📊 Tokens: {input_tokens} in | {output_tokens} out | {total_tokens} total{est_mark}")

