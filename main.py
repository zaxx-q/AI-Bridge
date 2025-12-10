#!/usr/bin/env python3
"""
AI Bridge - Multi-modal AI Assistant Server
Main entry point
"""

import sys
import threading
import signal
from pathlib import Path

from src.config import load_config, generate_example_config, CONFIG_FILE
from src.key_manager import KeyManager
from src.session_manager import load_sessions
from src.terminal import terminal_session_manager
from src.gui.core import HAVE_GUI
from src import web_server

# TextEditTool - now part of gui module
TEXT_EDIT_TOOL_APP = None
try:
    from src.gui import TextEditToolApp
    HAVE_TEXT_EDIT_TOOL = True
except ImportError as e:
    HAVE_TEXT_EDIT_TOOL = False
    print(f"[Note] TextEditTool not available: {e}")


def initialize():
    """Initialize the server"""
    print("=" * 60)
    print("AI Bridge - Multi-modal AI Assistant Server")
    print("=" * 60)
    
    print(f"\nLoading configuration from '{CONFIG_FILE}'...")
    config, ai_params, endpoints, keys = load_config()
    
    # Set global configuration
    web_server.CONFIG = config
    web_server.AI_PARAMS = ai_params
    web_server.ENDPOINTS = endpoints
    
    # Initialize key managers
    for provider in ["custom", "openrouter", "google"]:
        web_server.KEY_MANAGERS[provider] = KeyManager(keys[provider], provider)
        count = len(keys[provider])
        if count > 0:
            print(f"  ✓ {provider}: {count} API key(s) loaded")
        else:
            print(f"  ✗ {provider}: No API keys")
    
    print(f"\nLoading saved sessions...")
    load_sessions()
    
    print(f"\nServer Configuration:")
    print(f"  Host: {config.get('host', '127.0.0.1')}")
    print(f"  Port: {config.get('port', 5000)}")
    print(f"  Default Provider: {config.get('default_provider', 'google')}")
    show_setting = config.get('show_ai_response_in_chat_window', config.get('default_show', 'no'))
    print(f"  Show Response in Chat: {show_setting}")
    print(f"  GUI Available: {HAVE_GUI}")
    print(f"  GUI Mode: On-demand (starts when needed)")
    print(f"  Max Sessions: {config.get('max_sessions', 50)}")
    
    if ai_params:
        print(f"\nAI Parameters:")
        for k, v in ai_params.items():
            print(f"  {k}: {v}")
    
    print(f"\nRegistering {len(endpoints)} endpoint(s):")
    for endpoint_name, prompt in endpoints.items():
        prompt_preview = prompt[:60] + "..." if len(prompt) > 60 else prompt
        print(f"  /{endpoint_name}")
        print(f"      → {prompt_preview}")
    
    # Initialize web server with config and endpoints
    web_server.init_web_server(config, ai_params, endpoints, web_server.KEY_MANAGERS)
    
    print("\n" + "=" * 60)
    
    return config, ai_params


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
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create example config if needed
    if not Path(CONFIG_FILE).exists():
        print(f"Config file '{CONFIG_FILE}' not found.")
        print("Creating example configuration file...")
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write(generate_example_config())
        print(f"✓ Created '{CONFIG_FILE}'")
        print("\nPlease edit the config file to add your API keys, then restart.")
        sys.exit(0)
    
    # Initialize
    config, ai_params = initialize()
    
    # Check for API keys
    has_any_keys = any(km.has_keys() for km in web_server.KEY_MANAGERS.values())
    if not has_any_keys:
        print("\n⚠️  WARNING: No API keys configured!")
        print("Please add your API keys to config.ini\n")
    
    # NOTE: GUI is NOT started at startup - it will be started on-demand
    # when a GUI window is requested (via ?show=gui, ?show=chatgui, or pressing 'O')
    if HAVE_GUI:
        print("✓ GUI available (Tkinter, will start on-demand when needed)")
    else:
        print("✗ GUI not available")
    
    # Initialize TextEditTool
    initialize_text_edit_tool(config, ai_params)
    
    # Start terminal session manager
    terminal_thread = threading.Thread(target=terminal_session_manager, daemon=True)
    terminal_thread.start()
    
    # Start server
    host = web_server.CONFIG.get('host', '127.0.0.1')
    port = int(web_server.CONFIG.get('port', 5000))
    
    print(f"\n🚀 Starting server at http://{host}:{port}")
    print(f"   Endpoints: {', '.join('/' + e for e in web_server.ENDPOINTS.keys())}")
    print(f"\n   Show modes:")
    print(f"     ?show=no      - Return text only (default)")
    print(f"     ?show=yes     - Display result in chat GUI window")
    
    if TEXT_EDIT_TOOL_APP:
        hotkey = config.get("text_edit_tool_hotkey", "ctrl+space")
        print(f"\n   TextEditTool:")
        print(f"     Press '{hotkey}' to activate")
        print(f"     Options in text_edit_tool_options.json")
    
    print("\nPress Ctrl+C to stop\n")
    
    try:
        web_server.app.run(host=host, port=port)
    finally:
        cleanup()


if __name__ == '__main__':
    main()

