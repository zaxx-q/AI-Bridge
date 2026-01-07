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
from .console import console, Panel, Table, print_panel, print_success, print_error, print_warning, print_info, HAVE_RICH
from rich.align import Align
from rich.columns import Columns
from rich.text import Text


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
    if HAVE_RICH:
        commands_table = Table(box=None, show_header=False, padding=(0, 2))
        commands_table.add_column("Key", style="bold cyan", justify="right")
        commands_table.add_column("Action", style="white")
        commands_table.add_column("Key", style="bold cyan", justify="right")
        commands_table.add_column("Action", style="white")
        
        commands_table.add_row("[L]", "📋 Sessions", "[P]", "🔄 Provider")
        commands_table.add_row("[O]", "🖥️ Browser", "[M]", "🤖 Models")
        commands_table.add_row("[E]", "📡 Endpoints", "[S]", "📊 Status")
        commands_table.add_row("[G]", "⚙️ Settings", "[W]", "✏️ Prompts")
        commands_table.add_row("[T]", "💭 Thinking", "[R]", "🌊 Streaming")
        commands_table.add_row("[H]", "❓ Help", "", "")
        
        console.print(Panel(
            Align.center(commands_table),
            title="[bold]COMMANDS[/bold]",
            subtitle="[dim]Ctrl+C to stop[/dim]",
            border_style="blue",
        ))
        console.print()
    else:
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
                if HAVE_RICH:
                    table = Table(title=f"📡 Endpoints ({len(_endpoints)} registered)", box=None)
                    table.add_column("Path", style="bold green")
                    table.add_column("System Prompt Preview", style="dim")
                    
                    if not _endpoints:
                        console.print(Panel("No endpoints registered", style="yellow"))
                    else:
                        for name, prompt in _endpoints.items():
                            preview = prompt[:60] + "..." if len(prompt) > 60 else prompt
                            table.add_row(f"/{name}", preview)
                        console.print(table)
                        console.print()
                else:
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
                
                if HAVE_RICH:
                    console.print("[bold]🤖 Model Management[/bold]")
                
                provider = web_server.CONFIG.get("default_provider", "custom")
                current_model = web_server.CONFIG.get(f"{provider}_model", "not set")
                
                if HAVE_RICH:
                    console.print(f"   Provider: [cyan]{provider}[/cyan]")
                    console.print(f"   Current:  [green]{current_model}[/green]")
                    with console.status("[bold blue]Fetching available models...[/bold blue]"):
                        models, error = fetch_models(web_server.CONFIG, web_server.KEY_MANAGERS)
                else:
                    print(f"\n{'─'*64}")
                    print("🤖 MODEL MANAGEMENT")
                    print(f"{'─'*64}")
                    print(f"   Provider: {provider}")
                    print(f"   Current:  {current_model}")
                    print(f"\n   Fetching available models...")
                    models, error = fetch_models(web_server.CONFIG, web_server.KEY_MANAGERS)
                
                if error:
                    if HAVE_RICH:
                        print_error(error)
                    else:
                        print(f"   ✗ {error}")
                elif models:
                    if HAVE_RICH:
                        table = Table(show_header=True, box=None)
                        table.add_column("#", style="dim", justify="right")
                        table.add_column("Model ID", style="bold")
                        table.add_column("Context", style="dim")
                        
                        for i, m in enumerate(models):
                            marker = " [bold green]◄[/bold green]" if m['id'] == current_model else ""
                            ctx = str(m.get('context_length', '?'))
                            table.add_row(str(i+1), f"{m['id']}{marker}", ctx)
                        
                        console.print(table)
                        console.print("\n   Enter number or model name (q = cancel): ", end="")
                    else:
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
                
                provider = web_server.CONFIG.get("default_provider", "google")
                model = web_server.CONFIG.get(f"{provider}_model", "not set")
                base_url = get_base_url_for_status(web_server.CONFIG, provider)
                streaming = web_server.CONFIG.get("streaming_enabled", True)
                thinking = web_server.CONFIG.get("thinking_enabled", False)
                
                if HAVE_RICH:
                    grid = Table.grid(expand=True, padding=(0, 2))
                    grid.add_column(justify="left")
                    grid.add_column(justify="left")
                    
                    # Provider Info
                    grid.add_row("[bold]📡 Provider[/bold]", f"[cyan]{provider}[/cyan]")
                    grid.add_row("[dim]   Base URL[/dim]", f"[dim]{base_url}[/dim]")
                    grid.add_row("[bold]🤖 Model[/bold]", f"[green]{model}[/green]")
                    
                    # Settings
                    stream_icon = "[green]ON[/green]" if streaming else "[red]OFF[/red]"
                    think_icon = "[green]ON[/green]" if thinking else "[red]OFF[/red]"
                    grid.add_row("[bold]🌊 Streaming[/bold]", stream_icon)
                    grid.add_row("[bold]💭 Thinking[/bold]", think_icon)
                    
                    if thinking:
                        thinking_output = web_server.CONFIG.get("thinking_output", "reasoning_content")
                        grid.add_row("[dim]   Output[/dim]", thinking_output)
                    
                    # Server
                    host = web_server.CONFIG.get("host", "127.0.0.1")
                    port = web_server.CONFIG.get("port", 5000)
                    grid.add_row("[bold]🚀 Server[/bold]", f"[link=http://{host}:{port}]http://{host}:{port}[/link]")
                    
                    # Keys
                    key_status = []
                    for p, km in web_server.KEY_MANAGERS.items():
                        count = km.get_key_count()
                        color = "green" if count > 0 else "red"
                        active = " [bold]◄[/bold]" if p == provider else ""
                        key_status.append(f"[{color}]{p}: {count}[/{color}]{active}")
                    
                    grid.add_row("[bold]🔑 API Keys[/bold]", ", ".join(key_status))
                    
                    console.print(Panel(grid, title="[bold]System Status[/bold]", border_style="blue"))
                    console.print()
                else:
                    print(f"\n{'─'*64}")
                    print("📊 STATUS")
                    print(f"{'─'*64}")
                    print(f"   📡 Provider:  {provider}")
                    print(f"      Base URL:  {base_url}")
                    print(f"   🤖 Model:     {model}")
                    stream_status = "✅ ON" if streaming else "✗ OFF"
                    think_status = "✅ ON" if thinking else "✗ OFF"
                    print(f"\n   🌊 Streaming: {stream_status}")
                    print(f"   💭 Thinking:  {think_status}")
                    host = web_server.CONFIG.get("host", "127.0.0.1")
                    port = web_server.CONFIG.get("port", 5000)
                    print(f"\n   🚀 Server:    http://{host}:{port}")
                    print(f"\n   🔑 API Keys:")
                    for p, km in web_server.KEY_MANAGERS.items():
                        count = km.get_key_count()
                        print(f"      {p}: {count}")
                    print(f"{'─'*64}\n")
            
            elif key == 't':
                # Toggle thinking mode
                from . import web_server
                from .config import save_config_value
                
                current = web_server.CONFIG.get("thinking_enabled", False)
                new_value = not current
                
                if save_config_value("thinking_enabled", new_value):
                    web_server.CONFIG["thinking_enabled"] = new_value
                    if HAVE_RICH:
                        status = "[green]ON[/green]" if new_value else "[red]OFF[/red]"
                        console.print(f"\n💭 Thinking: {status}")
                    else:
                        status = "✅ ON" if new_value else "✗ OFF"
                        print(f"\n💭 Thinking: {status}")
                else:
                    if HAVE_RICH:
                        print_error("Failed to toggle thinking")
                    else:
                        print("\n✗ Failed to toggle thinking")
                if HAVE_RICH: console.print()
                else: print()
            
            elif key == 'r':
                # Toggle streaming mode
                from . import web_server
                from .config import save_config_value
                
                current = web_server.CONFIG.get("streaming_enabled", True)
                new_value = not current
                
                if save_config_value("streaming_enabled", new_value):
                    web_server.CONFIG["streaming_enabled"] = new_value
                    if HAVE_RICH:
                        status = "[green]ON[/green]" if new_value else "[red]OFF[/red]"
                        console.print(f"\n🌊 Streaming: {status}\n")
                    else:
                        status = "✅ ON" if new_value else "✗ OFF"
                        print(f"\n🌊 Streaming: {status}\n")
                else:
                    if HAVE_RICH:
                        print_error("Failed to toggle streaming")
                    else:
                        print("\n✗ Failed to toggle streaming\n")
            
            elif key == 'v':
                if HAVE_RICH:
                    console.print("\n[bold]Enter session ID: [/bold]", end="")
                else:
                    print("\nEnter session ID: ", end='', flush=True)
                try:
                    session_id = input().strip()
                    session = get_session(session_id)
                    if session:
                        if HAVE_RICH:
                            console.print(Panel(
                                f"[bold]Title:[/bold] {session.title}\n"
                                f"[dim]Endpoint:[/dim] {session.endpoint}\n"
                                f"[dim]Created:[/dim] {session.created_at}",
                                title=f"📋 Session: {session.session_id}"
                            ))
                            for msg in session.messages:
                                role_style = "green" if msg["role"] == "user" else "blue"
                                role_name = "User" if msg["role"] == "user" else "AI"
                                content = msg['content'][:500] + ('...' if len(msg['content']) > 500 else '')
                                console.print(Panel(content, title=f"[{role_style}]{role_name}[/{role_style}]", border_style=role_style))
                        else:
                            print(f"\n{'─'*64}")
                            print(f"📋 SESSION: {session.session_id}")
                            print(f"{'─'*64}")
                            print(f"   Title:    {session.title}")
                            # ... (keep existing non-rich code implicitly via structure, but simplified here for diff)
                            # Actually I should keep the fallback complete for safety
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
    
    if HAVE_RICH:
        console.print(f"{prefix}[dim]📊 Tokens: [bold green]{input_tokens}[/bold green] in | [bold blue]{output_tokens}[/bold blue] out | [bold white]{total_tokens}[/bold white] total{est_mark}[/dim]")
    else:
        print(f"{prefix}📊 Tokens: {input_tokens} in | {output_tokens} out | {total_tokens} total{est_mark}")

