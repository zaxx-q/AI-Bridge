#!/usr/bin/env python3
"""
AI Bridge - Multi-modal AI Assistant Server
Main entry point
"""

import sys
import logging
import threading
import signal
from pathlib import Path

from src.config import load_config, generate_example_config, CONFIG_FILE, OPENROUTER_URL
from src.key_manager import KeyManager
from src.session_manager import load_sessions, list_sessions
from src.terminal import terminal_session_manager, print_commands_box
from src.gui.core import HAVE_GUI
from src import web_server

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
    
    print("⚙️  Configuration")
    print(f"    📡 Provider:  {provider} → {base_url}")
    print(f"    🤖 Model:     {model}")
    stream_icon = "✅" if streaming else "✗"
    think_icon = "✅" if thinking else "✗"
    print(f"    🌊 Streaming: {stream_icon}")
    print(f"    💭 Thinking:  {think_icon}")
    print()
    
    # ─── API Keys ─────────────────────────────────────────────────────────
    print("🔑 API Keys")
    key_status = []
    for p in ["custom", "openrouter", "google"]:
        count = web_server.KEY_MANAGERS[p].get_key_count()
        if count > 0:
            marker = " ◄" if p == provider else ""
            key_status.append(f"✅ {p} ({count}){marker}")
        else:
            key_status.append(f"✗ {p}")
    print(f"    {key_status[0]}   {key_status[1]}   {key_status[2]}")
    print()
    
    # ─── Sessions ─────────────────────────────────────────────────────────
    load_sessions()
    sessions = list_sessions()
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


def main():
    """Main entry point"""
    # Suppress Flask/werkzeug logging (only show errors)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create example config if needed
    if not Path(CONFIG_FILE).exists():
        print(f"Config file '{CONFIG_FILE}' not found.")
        print("Creating example configuration file...")
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write(generate_example_config())
        print(f"✅ Created '{CONFIG_FILE}'")
        print("\nPlease edit the config file to add your API keys, then restart.")
        sys.exit(0)
    
    # Initialize (new compact output)
    config, ai_params, endpoints = initialize()
    
    # Check for API keys
    has_any_keys = any(km.has_keys() for km in web_server.KEY_MANAGERS.values())
    if not has_any_keys:
        print("⚠️  WARNING: No API keys configured!")
        print("   Please add your API keys to config.ini")
        print()
    
    # ─── Server Info ──────────────────────────────────────────────────────
    host = web_server.CONFIG.get('host', '127.0.0.1')
    port = int(web_server.CONFIG.get('port', 5000))
    
    print(f"🚀 Server: http://{host}:{port}")
    print(f"   📡  {len(endpoints)} endpoints registered")
    
    # GUI status
    if HAVE_GUI:
        print("   🖥️  GUI available (on-demand)")
    
    # TextEditTool
    text_tool_result = initialize_text_edit_tool(config, ai_params)
    if text_tool_result:
        hotkey = config.get("text_edit_tool_hotkey", "ctrl+space")
    
    print()
    
    # Start terminal session manager (also prints commands box)
    terminal_thread = threading.Thread(
        target=lambda: terminal_session_manager(endpoints),
        daemon=True
    )
    terminal_thread.start()
    
    try:
        # Run Flask with minimal output
        web_server.app.run(host=host, port=port, use_reloader=False)
    finally:
        cleanup()


if __name__ == '__main__':
    main()

