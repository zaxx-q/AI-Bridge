#!/usr/bin/env python3
"""
Terminal interactive session manager with enhanced console UI
"""

import sys
import time

from .session_manager import (
    list_sessions, get_session, delete_session, save_sessions,
    CHAT_SESSIONS, SESSION_LOCK, clear_all_sessions
)
from .gui.core import show_session_browser, get_gui_status, HAVE_GUI
from .config import OPENROUTER_URL


def get_base_url_for_status(config, provider):
    """Get the base URL for a provider (for status display)"""
    if provider == "custom":
        url = config.get("custom_url", "")
        if url:
            # Extract base URL (remove /chat/completions if present)
            if "/chat/completions" in url:
                url = url.replace("/chat/completions", "")
            return url
        return "Not configured"
    elif provider == "openrouter":
        return "openrouter.ai/api/v1"
    elif provider == "google":
        return "generativelanguage.googleapis.com"
    return "Unknown"


def print_commands_box():
    """Print the terminal commands box"""
    print("─" * 64)
    print("  COMMANDS                                       Ctrl+C to stop")
    print("─" * 64)
    print("  [L] 📋 Sessions      [P] 🔄 Provider     [T] 💭 Thinking")
    print("  [O] 🖥️ Browser       [M] 🤖 Models       [R] 🌊 Streaming")
    print("  [E] 📡 Endpoints     [S] 📊 Status       [H] ❓ Help")
    print("  [G] ⚙️ Settings      [W] ✏️ Prompts")
    print("─" * 64)
    print()


def terminal_session_manager(endpoints=None):
    """Interactive terminal session manager"""
    # Print the commands box
    print_commands_box()
    
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
    
    # Store endpoints reference
    _endpoints = endpoints or {}
    
    while True:
        try:
            key = get_input_nonblocking()
            
            if key == 'l':
                sessions = list_sessions()
                print(f"\n{'─'*64}")
                print(f"📋 SESSIONS ({len(sessions)} total)")
                print(f"{'─'*64}")
                if not sessions:
                    print("   (No sessions)")
                else:
                    for i, s in enumerate(sessions):
                        print(f"   [{s['id']}] {s['title'][:35]} ({s['messages']} msgs, {s['endpoint']})")
                print(f"{'─'*64}\n")
            
            elif key == 'o':
                if HAVE_GUI:
                    print("\n🖥️  Opening session browser...\n")
                    show_session_browser()
                else:
                    print("\n✗ GUI not available\n")
            
            elif key == 'e':
                # List endpoints
                print(f"\n{'─'*64}")
                print(f"📡 ENDPOINTS ({len(_endpoints)} registered)")
                print(f"{'─'*64}")
                if not _endpoints:
                    print("   (No endpoints)")
                else:
                    for name, prompt in _endpoints.items():
                        preview = prompt[:50] + "..." if len(prompt) > 50 else prompt
                        print(f"   /{name}")
                        print(f"      → {preview}")
                print(f"{'─'*64}\n")
            
            elif key == 'm':
                # Model management
                from . import web_server
                from .api_client import fetch_models
                from .config import save_config_value
                
                print(f"\n{'─'*64}")
                print("🤖 MODEL MANAGEMENT")
                print(f"{'─'*64}")
                provider = web_server.CONFIG.get("default_provider", "custom")
                current_model = web_server.CONFIG.get(f"{provider}_model", "not set")
                print(f"   Provider: {provider}")
                print(f"   Current:  {current_model}")
                print(f"\n   Fetching available models...")
                
                models, error = fetch_models(web_server.CONFIG, web_server.KEY_MANAGERS)
                if error:
                    print(f"   ✗ {error}")
                elif models:
                    print(f"\n   Available ({len(models)}):")
                    for i, m in enumerate(models):
                        marker = " ◄" if m['id'] == current_model else ""
                        print(f"      [{i+1:2}] {m['id']}{marker}")
                    
                    print("\n   Enter number or model name (q = cancel): ", end='', flush=True)
                    try:
                        choice = input().strip()
                        if choice.lower() != 'q':
                            try:
                                idx = int(choice) - 1
                                if 0 <= idx < len(models):
                                    new_model = models[idx]['id']
                                else:
                                    new_model = choice
                            except ValueError:
                                new_model = choice
                            
                            config_key = f"{provider}_model"
                            if save_config_value(config_key, new_model):
                                web_server.CONFIG[config_key] = new_model
                                print(f"   ✅ Model: {new_model}")
                            else:
                                print(f"   ✗ Failed to save")
                    except:
                        pass
                else:
                    print("   No models available")
                print(f"{'─'*64}\n")
            
            elif key == 'p':
                # Provider management
                from . import web_server
                from .config import save_config_value
                
                print(f"\n{'─'*64}")
                print("🔄 PROVIDER")
                print(f"{'─'*64}")
                current_provider = web_server.CONFIG.get("default_provider", "google")
                base_url = get_base_url_for_status(web_server.CONFIG, current_provider)
                print(f"   Current: {current_provider} → {base_url}")
                print()
                
                # List available providers
                available = []
                for p, km in web_server.KEY_MANAGERS.items():
                    key_count = km.get_key_count()
                    key_icon = "✅" if key_count > 0 else "✗"
                    key_info = f"({key_count})" if key_count > 0 else "(no keys)"
                    available.append((p, key_count))
                    marker = " ◄" if p == current_provider else ""
                    print(f"      [{len(available)}] {key_icon} {p} {key_info}{marker}")
                
                print("\n   Enter number or name (q = cancel): ", end='', flush=True)
                try:
                    choice = input().strip()
                    if choice.lower() != 'q' and choice:
                        try:
                            idx = int(choice) - 1
                            if 0 <= idx < len(available):
                                new_provider = available[idx][0]
                            else:
                                new_provider = choice.lower()
                        except ValueError:
                            new_provider = choice.lower()
                        
                        if new_provider in web_server.KEY_MANAGERS:
                            if save_config_value("default_provider", new_provider):
                                web_server.CONFIG["default_provider"] = new_provider
                                new_base = get_base_url_for_status(web_server.CONFIG, new_provider)
                                model = web_server.CONFIG.get(f"{new_provider}_model", "not set")
                                print(f"   ✅ {new_provider} → {new_base}")
                                print(f"     Model: {model}")
                            else:
                                print(f"   ✗ Failed to save")
                        else:
                            print(f"   ✗ Unknown: {new_provider}")
                except:
                    pass
                print(f"{'─'*64}\n")
            
            elif key == 's':
                # Status command - enhanced with base_url
                from . import web_server
                
                print(f"\n{'─'*64}")
                print("📊 STATUS")
                print(f"{'─'*64}")
                
                # Provider/Model with base URL
                provider = web_server.CONFIG.get("default_provider", "google")
                model = web_server.CONFIG.get(f"{provider}_model", "not set")
                base_url = get_base_url_for_status(web_server.CONFIG, provider)
                
                print(f"   📡 Provider:  {provider}")
                print(f"      Base URL:  {base_url}")
                print(f"   🤖 Model:     {model}")
                
                # Streaming/Thinking
                streaming = web_server.CONFIG.get("streaming_enabled", True)
                thinking = web_server.CONFIG.get("thinking_enabled", False)
                stream_status = "✅ ON" if streaming else "✗ OFF"
                think_status = "✅ ON" if thinking else "✗ OFF"
                print(f"\n   🌊 Streaming: {stream_status}")
                print(f"   💭 Thinking:  {think_status}")
                
                if thinking:
                    thinking_output = web_server.CONFIG.get("thinking_output", "reasoning_content")
                    print(f"      Output: {thinking_output}")
                    if provider == "google":
                        budget = web_server.CONFIG.get("thinking_budget", -1)
                        level = web_server.CONFIG.get("thinking_level", "high")
                        print(f"      Budget: {budget} | Level: {level}")
                    else:
                        effort = web_server.CONFIG.get("reasoning_effort", "high")
                        print(f"      Effort: {effort}")
                
                # Server
                host = web_server.CONFIG.get("host", "127.0.0.1")
                port = web_server.CONFIG.get("port", 5000)
                print(f"\n   🚀 Server:    http://{host}:{port}")
                
                # Sessions
                sessions = list_sessions()
                print(f"   📂 Sessions:  {len(sessions)} saved")
                
                # API Keys
                print(f"\n   🔑 API Keys:")
                for p, km in web_server.KEY_MANAGERS.items():
                    count = km.get_key_count()
                    key_icon = "✅" if count > 0 else "✗"
                    marker = " ◄" if p == provider else ""
                    print(f"      {key_icon} {p}: {count} key{'s' if count != 1 else ''}{marker}")
                
                print(f"{'─'*64}\n")
            
            elif key == 't':
                # Toggle thinking mode
                from . import web_server
                from .config import save_config_value
                
                current = web_server.CONFIG.get("thinking_enabled", False)
                new_value = not current
                
                if save_config_value("thinking_enabled", new_value):
                    web_server.CONFIG["thinking_enabled"] = new_value
                    status = "✅ ON" if new_value else "✗ OFF"
                    print(f"\n💭 Thinking: {status}")
                    if new_value:
                        output_mode = web_server.CONFIG.get("thinking_output", "reasoning_content")
                        print(f"   Output: {output_mode}")
                else:
                    print("\n✗ Failed to toggle thinking")
                print()
            
            elif key == 'r':
                # Toggle streaming mode
                from . import web_server
                from .config import save_config_value
                
                current = web_server.CONFIG.get("streaming_enabled", True)
                new_value = not current
                
                if save_config_value("streaming_enabled", new_value):
                    web_server.CONFIG["streaming_enabled"] = new_value
                    status = "✅ ON" if new_value else "✗ OFF"
                    print(f"\n🌊 Streaming: {status}\n")
                else:
                    print("\n✗ Failed to toggle streaming\n")
            
            elif key == 'v':
                print("\nEnter session ID: ", end='', flush=True)
                try:
                    session_id = input().strip()
                    session = get_session(session_id)
                    if session:
                        print(f"\n{'─'*64}")
                        print(f"📋 SESSION: {session.session_id}")
                        print(f"{'─'*64}")
                        print(f"   Title:    {session.title}")
                        print(f"   Endpoint: {session.endpoint}")
                        print(f"   Created:  {session.created_at}")
                        print(f"{'─'*64}")
                        for msg in session.messages:
                            role_icon = "👤" if msg["role"] == "user" else "🤖"
                            role = "USER" if msg["role"] == "user" else "AI"
                            print(f"\n{role_icon} [{role}]")
                            print(msg['content'][:500] + ('...' if len(msg['content']) > 500 else ''))
                        print(f"{'─'*64}\n")
                        
                        if HAVE_GUI:
                            open_gui = input("Open in GUI? [y/N]: ").strip().lower()
                            if open_gui == 'y':
                                from .gui.core import show_chat_gui
                                show_chat_gui(session)
                    else:
                        print(f"✗ Session '{session_id}' not found.\n")
                except:
                    pass
            
            elif key == 'd':
                print("\nEnter session ID to delete: ", end='', flush=True)
                try:
                    session_id = input().strip()
                    if get_session(session_id):
                        confirm = input(f"Delete {session_id}? [y/N]: ").strip().lower()
                        if confirm == 'y':
                            if delete_session(session_id):
                                save_sessions()
                                print(f"✅ Session {session_id} deleted.\n")
                    else:
                        print(f"✗ Session '{session_id}' not found.\n")
                except:
                    pass
            
            elif key == 'c':
                try:
                    confirm = input("\n⚠️  Clear ALL sessions? [y/N]: ").strip().lower()
                    if confirm == 'y':
                        clear_all_sessions()
                        save_sessions()
                        print("✅ All sessions cleared.\n")
                except:
                    pass
            
            elif key == 'g':
                # Open Settings window
                if HAVE_GUI:
                    print("\n⚙️  Opening settings...\n")
                    from .gui.core import show_settings_window
                    show_settings_window()
                else:
                    print("\n✗ GUI not available\n")
            
            elif key == 'w':
                # Open Prompt Editor window
                if HAVE_GUI:
                    print("\n✏️  Opening prompt editor...\n")
                    from .gui.core import show_prompt_editor
                    show_prompt_editor()
                else:
                    print("\n✗ GUI not available\n")
            
            elif key == 'h':
                print(f"\n{'─'*64}")
                print("❓ HELP")
                print(f"{'─'*64}")
                print("   [L] 📋 Sessions      List recent saved sessions")
                print("   [O] 🖥️ Browser       Open session browser GUI")
                print("   [V] 👁️ View          View a session by ID")
                print("   [D] 🗑️ Delete        Delete a session by ID")
                print("   [C] 🧹 Clear         Clear all sessions")
                print("   [E] 📡 Endpoints     List registered endpoints")
                print("   [M] 🤖 Models        List/set models from API")
                print("   [P] 🔄 Provider      Switch API provider")
                print("   [S] 📊 Status        Show current configuration")
                print("   [T] 💭 Thinking      Toggle thinking mode")
                print("   [R] 🌊 Streaming     Toggle streaming")
                print("   [G] ⚙️ Settings      Open settings window")
                print("   [W] ✏️ Prompts       Open prompt editor")
                print("   [H] ❓ Help          Show this help")
                print(f"{'─'*64}\n")
            
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

