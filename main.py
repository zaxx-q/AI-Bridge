#!/usr/bin/env python3
"""
AI Bridge - Multi-modal AI Assistant Server
Main entry point

Usage:
    python main.py              # Start with tray (console hidden)
    python main.py --no-tray    # Start in terminal mode (no tray)
    python main.py --show-console   # Start with tray + console visible
"""

import sys
import socket
import logging
import threading
import signal
import argparse
from pathlib import Path

# Rich console for beautiful output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import print as rprint
    HAVE_RICH = True
    console = Console()
except ImportError:
    HAVE_RICH = False
    console = None

from src.config import load_config, generate_example_config, CONFIG_FILE, OPENROUTER_URL
from src.key_manager import KeyManager
from src.session_manager import load_sessions, list_sessions
from src.terminal import terminal_session_manager, print_commands_box
from src.gui.core import HAVE_GUI
from src import web_server

# System tray support
HAVE_TRAY = False
try:
    from src.tray import TrayApp, hide_console, show_console, HAVE_SYSTRAY
    HAVE_TRAY = HAVE_SYSTRAY
except ImportError:
    pass

# TextEditTool - now part of gui module
TEXT_EDIT_TOOL_APP = None
try:
    from src.gui import TextEditToolApp
    HAVE_TEXT_EDIT_TOOL = True
except ImportError as e:
    HAVE_TEXT_EDIT_TOOL = False
    # Silent - will show in startup


def get_base_url(config, provider):
    """Get the base URL for a provider"""
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


def initialize():
    """Initialize the server with compact, informative output"""
    
    # ─── Banner ───────────────────────────────────────────────────────────
    if HAVE_RICH:
        console.print()
        console.print(Panel.fit(
            "[bold cyan]🌉 AI Bridge[/bold cyan]\n[dim]Multi-modal AI Assistant Server[/dim]",
            border_style="cyan"
        ))
        console.print()
    else:
        print()
        print("┌" + "─" * 62 + "┐")
        print("│  🌉 AI Bridge                                                 │")
        print("│  Multi-modal AI Assistant Server                              │")
        print("└" + "─" * 62 + "┘")
        print()
    
    # Load configuration
    config, ai_params, endpoints, keys = load_config()
    
    # Set global configuration
    web_server.CONFIG = config
    web_server.AI_PARAMS = ai_params
    web_server.ENDPOINTS = endpoints
    
    # Initialize key managers
    for provider in ["custom", "openrouter", "google"]:
        web_server.KEY_MANAGERS[provider] = KeyManager(keys[provider], provider)
    
    # ─── Configuration Summary ────────────────────────────────────────────
    provider = config.get('default_provider', 'google')
    model = config.get(f'{provider}_model', 'not set')
    base_url = get_base_url(config, provider)
    streaming = config.get('streaming_enabled', True)
    thinking = config.get('thinking_enabled', False)
    
    if HAVE_RICH:
        # Create a nice table for configuration
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="dim")
        table.add_column("Value")
        
        table.add_row("📡 Provider", f"[cyan]{provider}[/cyan] → [dim]{base_url}[/dim]")
        table.add_row("🤖 Model", f"[green]{model}[/green]")
        stream_icon = "[green]✓[/green]" if streaming else "[red]✗[/red]"
        think_icon = "[green]✓[/green]" if thinking else "[red]✗[/red]"
        table.add_row("🌊 Streaming", stream_icon)
        table.add_row("💭 Thinking", think_icon)
        
        console.print("[bold]⚙️  Configuration[/bold]")
        console.print(table)
        console.print()
    else:
        print("⚙️  Configuration")
        print(f"    📡 Provider:  {provider} → {base_url}")
        print(f"    🤖 Model:     {model}")
        stream_icon = "✓" if streaming else "✗"
        think_icon = "✓" if thinking else "✗"
        print(f"    🌊 Streaming: {stream_icon}")
        print(f"    💭 Thinking:  {think_icon}")
        print()
    
    # ─── API Keys ─────────────────────────────────────────────────────────
    if HAVE_RICH:
        key_parts = []
        for p in ["custom", "openrouter", "google"]:
            count = web_server.KEY_MANAGERS[p].get_key_count()
            if count > 0:
                marker = " ◄" if p == provider else ""
                key_parts.append(f"[green]✓[/green] {p} ({count}){marker}")
            else:
                key_parts.append(f"[red]✗[/red] {p}")
        console.print(f"[bold]🔑 API Keys[/bold]  {key_parts[0]}  {key_parts[1]}  {key_parts[2]}")
        console.print()
    else:
        print("🔑 API Keys")
        key_status = []
        for p in ["custom", "openrouter", "google"]:
            count = web_server.KEY_MANAGERS[p].get_key_count()
            if count > 0:
                marker = " ◄" if p == provider else ""
                key_status.append(f"✓ {p} ({count}){marker}")
            else:
                key_status.append(f"✗ {p}")
        print(f"    {key_status[0]}   {key_status[1]}   {key_status[2]}")
        print()
    
    # ─── Sessions ─────────────────────────────────────────────────────────
    load_sessions()
    sessions = list_sessions()
    if HAVE_RICH:
        console.print(f"[bold]📂 Sessions[/bold]  {len(sessions)} loaded")
        console.print()
    else:
        print(f"📂 Sessions: {len(sessions)} loaded")
        print()
    
    # Initialize web server (silent)
    web_server.init_web_server(config, ai_params, endpoints, web_server.KEY_MANAGERS)
    
    return config, ai_params, endpoints


def initialize_text_edit_tool(config, ai_params):
    """Initialize TextEditTool if enabled"""
    global TEXT_EDIT_TOOL_APP
    
    if not HAVE_TEXT_EDIT_TOOL:
        print("  ✗ TextEditTool: Not available (missing dependencies)")
        return None
    
    if not config.get("text_edit_tool_enabled", True):
        print("  ✗ TextEditTool: Disabled in config")
        return None
    
    try:
        print("\nInitializing TextEditTool...")
        TEXT_EDIT_TOOL_APP = TextEditToolApp(
            config=config,
            ai_params=ai_params,
            key_managers=web_server.KEY_MANAGERS,
            options_file="text_edit_tool_options.json"
        )
        TEXT_EDIT_TOOL_APP.start()
        
        # Register instance for hot-reload
        from src.gui.text_edit_tool import set_instance
        set_instance(TEXT_EDIT_TOOL_APP)
        
        return TEXT_EDIT_TOOL_APP
    except Exception as e:
        print(f"  ✗ TextEditTool: Failed to initialize: {e}")
        return None


def cleanup():
    """Cleanup on shutdown"""
    global TEXT_EDIT_TOOL_APP
    
    if TEXT_EDIT_TOOL_APP:
        print("\nStopping TextEditTool...")
        TEXT_EDIT_TOOL_APP.stop()
        TEXT_EDIT_TOOL_APP = None


def signal_handler(signum, frame):
    """Handle interrupt signals"""
    print("\n\nShutdown signal received...")
    cleanup()
    sys.exit(0)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="AI Bridge - Multi-modal AI Assistant Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                  Start with tray (console hidden by default)
  python main.py --no-tray        Start in terminal mode (no tray icon)
  python main.py --show-console   Start with tray and console visible
        """
    )
    parser.add_argument(
        '--no-tray',
        action='store_true',
        help='Run in terminal mode without system tray'
    )
    parser.add_argument(
        '--show-console',
        action='store_true',
        help='Start with console visible (when using tray mode)'
    )
    return parser.parse_args()


def check_port_available(host: str, port: int) -> bool:
    """
    Check if a port is available for binding.
    Returns True if available, False if already in use.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.bind((host, port))
        sock.close()
        return True
    except OSError:
        return False


def run_server(config, ai_params, endpoints):
    """Run the Flask server (used by both tray and terminal modes)"""
    host = web_server.CONFIG.get('host', '127.0.0.1')
    port = int(web_server.CONFIG.get('port', 5000))
    
    try:
        # Run Flask with minimal output
        web_server.app.run(host=host, port=port, use_reloader=False, threaded=True)
    finally:
        cleanup()


def main():
    """Main entry point"""
    # Parse command line arguments
    args = parse_args()
    
    # Suppress Flask/werkzeug logging (only show errors)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    
    # Suppress Flask startup banner
    import flask.cli
    flask.cli.show_server_banner = lambda *args: None
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create example config if needed (don't use tray mode for first-run config creation)
    if not Path(CONFIG_FILE).exists():
        if HAVE_RICH:
            console.print(f"[yellow]Config file '{CONFIG_FILE}' not found.[/yellow]")
            console.print("Creating example configuration file...")
        else:
            print(f"Config file '{CONFIG_FILE}' not found.")
            print("Creating example configuration file...")
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write(generate_example_config())
        if HAVE_RICH:
            console.print(f"[green]✅ Created '{CONFIG_FILE}'[/green]")
            console.print("\nPlease edit the config file to add your API keys, then restart.")
            console.print("[dim]Press Enter to exit...[/dim]")
        else:
            print(f"✅ Created '{CONFIG_FILE}'")
            print("\nPlease edit the config file to add your API keys, then restart.")
            print("Press Enter to exit...")
        input()  # Wait for user to read the message
        sys.exit(0)
    
    # Initialize (new compact output)
    config, ai_params, endpoints = initialize()
    
    # Check for API keys
    has_any_keys = any(km.has_keys() for km in web_server.KEY_MANAGERS.values())
    if not has_any_keys:
        if HAVE_RICH:
            console.print("[bold yellow]⚠️  WARNING: No API keys configured![/bold yellow]")
            console.print("   Please add your API keys to [cyan]config.ini[/cyan]")
            console.print()
        else:
            print("⚠️  WARNING: No API keys configured!")
            print("   Please add your API keys to config.ini")
            print()
    
    # ─── Server Info ──────────────────────────────────────────────────────
    host = web_server.CONFIG.get('host', '127.0.0.1')
    port = int(web_server.CONFIG.get('port', 5000))
    
    # Check if port is available (single instance check)
    if not check_port_available(host, port):
        if HAVE_RICH:
            console.print()
            console.print(f"[bold red]❌ ERROR: Port {port} is already in use![/bold red]")
            console.print()
            console.print("[yellow]Another instance of AI Bridge may already be running.[/yellow]")
            console.print(f"[dim]Check if port {port} is in use: netstat -an | findstr {port}[/dim]")
            console.print()
            console.print("[dim]Press Enter to exit...[/dim]")
        else:
            print()
            print(f"❌ ERROR: Port {port} is already in use!")
            print()
            print("Another instance of AI Bridge may already be running.")
            print(f"Check if port {port} is in use: netstat -an | findstr {port}")
            print()
            print("Press Enter to exit...")
        input()
        sys.exit(1)
    
    if HAVE_RICH:
        console.print(f"[bold green]🚀 Server[/bold green]  [link=http://{host}:{port}]http://{host}:{port}[/link]")
        console.print(f"   📡  {len(endpoints)} endpoints registered")
        if HAVE_GUI:
            console.print("   🖥️  GUI available (on-demand)")
    else:
        print(f"🚀 Server: http://{host}:{port}")
        print(f"   📡  {len(endpoints)} endpoints registered")
        if HAVE_GUI:
            print("   🖥️  GUI available (on-demand)")
    
    # TextEditTool
    text_tool_result = initialize_text_edit_tool(config, ai_params)
    if text_tool_result:
        hotkey = config.get("text_edit_tool_hotkey", "ctrl+space")
    
    print()
    
    # ─── Tray Mode vs Terminal Mode ───────────────────────────────────────
    use_tray = HAVE_TRAY and not args.no_tray and sys.platform == 'win32'
    
    if use_tray:
        # Tray mode: hide console by default, run server in background
        if HAVE_RICH:
            console.print("[bold blue]🔲 Starting in tray mode...[/bold blue]")
            console.print("   Right-click tray icon for menu")
            console.print("   Double-click tray icon to show console")
            console.print()
        else:
            print("🔲 Starting in tray mode...")
            print("   Right-click tray icon for menu")
            print("   Double-click tray icon to show console")
            print()
        
        # Start terminal session manager
        terminal_thread = threading.Thread(
            target=lambda: terminal_session_manager(endpoints),
            daemon=True
        )
        terminal_thread.start()
        
        # Start Flask server in background thread
        server_thread = threading.Thread(
            target=lambda: run_server(config, ai_params, endpoints),
            daemon=True
        )
        server_thread.start()
        
        # Start tray (this blocks until exit)
        tray = TrayApp(on_exit_callback=cleanup)
        hide_on_start = not args.show_console
        tray.start(hide_console_on_start=hide_on_start)
        
    else:
        # Terminal mode: normal behavior
        if args.no_tray:
            if HAVE_RICH:
                console.print("[dim]📟 Running in terminal mode (--no-tray)[/dim]")
            else:
                print("📟 Running in terminal mode (--no-tray)")
        elif not HAVE_TRAY:
            if HAVE_RICH:
                console.print("[dim]📟 Running in terminal mode (tray not available)[/dim]")
                console.print("   Install with: [cyan]pip install infi.systray[/cyan]")
            else:
                print("📟 Running in terminal mode (tray not available)")
                print("   Install with: pip install infi.systray")
        print()
        
        # Start terminal session manager
        terminal_thread = threading.Thread(
            target=lambda: terminal_session_manager(endpoints),
            daemon=True
        )
        terminal_thread.start()
        
        # Run server in main thread
        run_server(config, ai_params, endpoints)


if __name__ == '__main__':
    main()

