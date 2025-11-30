#!/usr/bin/env python3
"""
Universal ShareX Middleman Server with GUI Support (Dear PyGui)
Main entry point
"""

import sys
import threading
from pathlib import Path

from src.config import load_config, generate_example_config, CONFIG_FILE
from src.key_manager import KeyManager
from src.session_manager import load_sessions
from src.terminal import terminal_session_manager
from src.gui.core import HAVE_GUI
from src import web_server


def initialize():
    """Initialize the server"""
    print("=" * 60)
    print("Universal ShareX Middleman Server (Dear PyGui - On Demand)")
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
    print(f"  Default Show Mode: {config.get('default_show', 'no')}")
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
    
    # Register endpoints with Flask
    web_server.register_endpoints(endpoints)
    
    print("\n" + "=" * 60)


def main():
    """Main entry point"""
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
    initialize()
    
    # Check for API keys
    has_any_keys = any(km.has_keys() for km in web_server.KEY_MANAGERS.values())
    if not has_any_keys:
        print("\n⚠️  WARNING: No API keys configured!")
        print("Please add your API keys to config.ini\n")
    
    # NOTE: GUI is NOT started at startup - it will be started on-demand
    # when a GUI window is requested (via ?show=gui, ?show=chatgui, or pressing 'O')
    if HAVE_GUI:
        print("✓ GUI available (will start on-demand when needed)")
    else:
        print("✗ GUI not available (Dear PyGui not installed)")
    
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
    print(f"     ?show=gui     - Display result in GUI window (starts GUI on first use)")
    print(f"     ?show=chatgui - Display result in chat GUI with follow-up input")
    print("\nPress Ctrl+C to stop\n")
    
    web_server.run_server(host, port)


if __name__ == '__main__':
    main()
