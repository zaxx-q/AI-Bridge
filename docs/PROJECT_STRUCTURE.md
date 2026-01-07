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
    ├── console.py              # Centralized Rich console configuration
    ├── key_manager.py          # API key rotation with exhaustion tracking
    ├── request_pipeline.py     # Unified request processing with logging
    ├── session_manager.py      # Session persistence with sequential IDs
    ├── terminal.py             # Interactive terminal commands
    ├── tray.py                 # System tray application (Windows)
    ├── utils.py                # Utility functions (strip_markdown, etc.)
    ├── web_server.py           # Flask server and API endpoints
    │
    ├── gui/                    # GUI Package (CustomTkinter)
    │   ├── __init__.py
    │   ├── core.py             # GUICoordinator singleton for thread-safe GUI
    │   ├── custom_widgets.py   # Reusable UI components (ScrollableButtonList)
    │   ├── emoji_renderer.py   # Twemoji-based color emoji support for Windows
    │   ├── hotkey.py           # Global hotkey listener (pynput)
    │   ├── options.py          # Default options and settings constants
    │   ├── popups.py           # Modern themed popups with scrollable ModifierBar
    │   ├── prompt_editor.py    # GUI editor for text_edit_tool_options.json
    │   ├── settings_window.py  # GUI editor for config.ini
    │   ├── text_edit_tool.py   # TextEditTool application controller
    │   ├── text_handler.py     # Text selection and replacement
    │   ├── themes.py           # ThemeRegistry with multi-theme support
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
| `console.py` | Centralized Rich console configuration with custom theme |
| `config.py` | Custom INI parser with multiline support |
| `key_manager.py` | Multi-key management with automatic rotation |
| `request_pipeline.py` | Unified logging and token tracking for all requests |
| `session_manager.py` | Chat session persistence to JSON |

### GUI (`src/gui/`)

| Module | Purpose |
|--------|---------|
| `core.py` | GUICoordinator singleton managing all CustomTkinter windows |
| `emoji_renderer.py` | EmojiRenderer for Windows color emoji support (Twemoji) |
| `custom_widgets.py` | Custom scrollable lists and emoji-aware buttons/headers |
| `text_edit_tool.py` | Global hotkey TextEditTool application |
| `windows.py` | Chat window and session browser implementations |
| `popups.py` | Themed popup dialogs with dual inputs (Edit/Ask) and scrollable ModifierBar |
| `hotkey.py` | pynput-based global hotkey listener |
| `themes.py` | ThemeRegistry with 7 themes, dark/light variants, system detection |
| `settings_window.py` | GUI editor for config.ini with tabbed interface |
| `prompt_editor.py` | GUI editor for text_edit_tool_options.json with hot-reload |

### Providers (`src/providers/`)

| Module | Purpose |
|--------|---------|
| `base.py` | Abstract BaseProvider with retry logic |
| `openai_compatible.py` | OpenAI API format (OpenRouter, custom endpoints) |
| `gemini_native.py` | Native Google Gemini API with thinking support |