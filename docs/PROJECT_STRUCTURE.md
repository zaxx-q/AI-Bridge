# Project Structure

AI Bridge follows a modular architecture separating the web server, GUI, system tray, and AI providers.

```
AI-Bridge/
├── main.py                     # Main entry point (--no-tray, --show-console flags)
├── setup.py                    # cx_Freeze build configuration for Windows executable
├── requirements.txt            # Python dependencies
├── config.ini                  # Configuration (auto-generated on first run)
├── chat_sessions.json          # Saved chat sessions (auto-created)
├── text_edit_tool_options.json # TextEditTool prompts and settings
├── icon.ico                    # System tray icon
├── LICENSE
├── README.md
├── AGENTS.md                   # AI agent guidance
│
├── docs/                       # Documentation
│   ├── PROJECT_STRUCTURE.md    # This file
│   ├── ARCHITECTURE.md         # Technical architecture details
│   └── SHAREX_SETUP.md         # ShareX integration guide
│
└── src/
    ├── __init__.py
    ├── api_client.py           # Unified API interface using providers
    ├── config.py               # Custom INI parser, configuration management
    ├── key_manager.py          # API key rotation with exhaustion tracking
    ├── request_pipeline.py     # Unified request processing with logging
    ├── session_manager.py      # Session persistence with sequential IDs
    ├── terminal.py             # Interactive terminal commands
    ├── tray.py                 # System tray application (Windows)
    ├── utils.py                # Utility functions (strip_markdown, etc.)
    ├── web_server.py           # Flask server and API endpoints
    │
    ├── gui/                    # GUI Package (Tkinter)
    │   ├── __init__.py
    │   ├── core.py             # GUICoordinator singleton for thread-safe GUI
    │   ├── hotkey.py           # Global hotkey listener (pynput)
    │   ├── options.py          # Default options and settings constants
    │   ├── popups.py           # Modern Catppuccin-styled popups
    │   ├── text_edit_tool.py   # TextEditTool application controller
    │   ├── text_handler.py     # Text selection and replacement
    │   ├── utils.py            # GUI utilities (clipboard, markdown render)
    │   └── windows.py          # Chat and Browser windows
    │
    └── providers/              # AI Provider Implementations
        ├── __init__.py         # Provider exports and factory
        ├── base.py             # Abstract base provider, retry logic, ProviderResult
        ├── gemini_native.py    # Native Gemini API with full feature support
        └── openai_compatible.py # OpenRouter, Custom, Google OpenAI-compat
```

## Key Modules

### Core (`src/`)

| Module | Purpose |
|--------|---------|
| `tray.py` | System tray icon with console show/hide, restart, session browser |
| `web_server.py` | Flask REST API endpoints for image processing |
| `terminal.py` | Interactive terminal commands when console is visible |
| `config.py` | Custom INI parser with multiline support |
| `key_manager.py` | Multi-key management with automatic rotation |
| `request_pipeline.py` | Unified logging and token tracking for all requests |
| `session_manager.py` | Chat session persistence to JSON |

### GUI (`src/gui/`)

| Module | Purpose |
|--------|---------|
| `core.py` | GUICoordinator singleton managing all Tkinter windows |
| `text_edit_tool.py` | Global hotkey TextEditTool application |
| `windows.py` | Chat window and session browser implementations |
| `popups.py` | Catppuccin-themed popup dialogs |
| `hotkey.py` | pynput-based global hotkey listener |

### Providers (`src/providers/`)

| Module | Purpose |
|--------|---------|
| `base.py` | Abstract BaseProvider with retry logic |
| `openai_compatible.py` | OpenAI API format (OpenRouter, custom endpoints) |
| `gemini_native.py` | Native Google Gemini API with thinking support |