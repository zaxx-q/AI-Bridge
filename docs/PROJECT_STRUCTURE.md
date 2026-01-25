# Project Structure

AIPromptBridge follows a modular architecture separating the web server, GUI, system tray, AI providers, and tools.

```
AIPromptBridge/
├── main.py                     # Main entry point (--no-tray, --show-console flags)
├── setup.py                    # cx_Freeze build configuration for Windows executable
├── requirements.txt            # Python dependencies
├── config.ini                  # Configuration (auto-generated on first run)
├── chat_sessions.json          # Saved chat sessions (auto-created)
├── prompts.json                # Unified prompt configuration (TextEdit, Snip, Endpoints)
├── tools_config.json           # Tools configuration (auto-generated on demand)
├── session_attachments/        # Directory for message attachment files
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
    ├── attachment_manager.py   # Persistent storage for session attachments
    ├── config.py               # Custom INI parser, configuration management
    ├── console.py              # Centralized Rich console configuration
    ├── key_manager.py          # API key rotation with exhaustion tracking
    ├── request_pipeline.py     # Unified request processing with logging
    ├── session_manager.py      # Session persistence with sequential IDs
    ├── terminal.py             # Interactive terminal commands (includes Tools menu)
    ├── tray.py                 # System tray application (Windows)
    ├── utils.py                # Utility functions (strip_markdown, etc.)
    ├── web_server.py           # Flask server and API endpoints
    │
    ├── gui/                    # GUI Package (CustomTkinter)
    │   ├── __init__.py
    │   ├── core.py             # GUICoordinator singleton for thread-safe GUI
    │   ├── custom_widgets.py   # Reusable UI components (ScrollableButtonList, ScrollableComboBox)
    │   ├── emoji_renderer.py   # Twemoji-based color emoji support for Windows
    │   ├── hotkey.py           # Global hotkey listener (pynput)
    │   ├── options.py          # Default options and settings constants (Deprecated)
    │   ├── platform.py         # UI toolkit authority (HAVE_CTK and fallback logic)
    │   ├── popups.py           # Modern themed popups with scrollable ModifierBar
    │   ├── prompt_editor.py    # GUI editor for prompts.json
    │   ├── prompts.py          # Unified PromptsConfig loader/manager
    │   ├── screen_snip.py      # Screenshot capture and overlay
    │   ├── settings_window.py  # GUI editor for config.ini
    │   ├── snip_popup.py       # Popup UI for screen snipping results
    │   ├── snip_tool.py        # Screen Snip controller application
    │   ├── text_edit_tool.py   # TextEditTool application controller
    │   ├── text_handler.py     # Text selection and replacement
    │   ├── themes.py           # ThemeRegistry with multi-theme support
    │   ├── utils.py            # GUI utilities (clipboard, markdown render)
    │   └── windows/            # Modular window implementations
    │       ├── __init__.py
    │       ├── base.py         # Base class for CTk windows
    │       ├── chat_window.py  # Interactive chat window
    │       ├── session_browser.py # Session history browser
    │       └── utils.py        # Window management utilities
    │
    ├── providers/              # AI Provider Implementations
    │   ├── __init__.py         # Provider exports and factory
    │   ├── base.py             # Abstract base provider, retry logic, ProviderResult
    │   ├── gemini_native.py    # Native Gemini API (Batch, Files API support)
    │   └── openai_compatible.py # OpenRouter, Custom, Google OpenAI-compat
    │
    └── tools/                  # Tools Package - Batch file processing
        ├── __init__.py         # Tool exports
        ├── audio_processor.py  # Audio optimization, chunking, and FFmpeg wrapper
        ├── base.py             # Abstract BaseTool class
        ├── checkpoint.py       # Checkpoint/resume system (Retry Checkpoint support)
        ├── config.py           # Tools configuration loader
        ├── file_handler.py     # File type detection, PDF support, multimodal handling
        └── file_processor.py   # Interactive File Processor (Batch/Files API logic)
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
| `attachment_manager.py`| Manages external file storage for session attachments |

### GUI (`src/gui/`)

| Module | Purpose |
|--------|---------|
| `core.py` | GUICoordinator singleton managing all CustomTkinter windows |
| `emoji_renderer.py` | EmojiRenderer for Windows color emoji support (Twemoji) |
| `custom_widgets.py` | Custom scrollable lists and emoji-aware dropdowns (ScrollableComboBox) |
| `text_edit_tool.py` | Global hotkey TextEditTool application |
| `snip_tool.py` | Screen Snipping application controller (`Ctrl+Shift+X`) |
| `platform.py` | Central authority for UI toolkit availability and toolkit fallback |
| `windows/` | Modular package for application windows |
| `popups.py` | Themed popup dialogs with dual inputs (Edit/Ask) and scrollable ModifierBar |
| `hotkey.py` | pynput-based global hotkey listener |
| `themes.py` | ThemeRegistry with 7 themes, dark/light variants, system detection |
| `settings_window.py` | GUI editor for config.ini with tabbed interface |
| `prompt_editor.py` | GUI editor for prompts.json with hot-reload |

### Providers (`src/providers/`)

| Module | Purpose |
|--------|---------|
| `base.py` | Abstract BaseProvider with retry logic |
| `openai_compatible.py` | OpenAI API format (OpenRouter, custom endpoints) |
| `gemini_native.py` | Native Google Gemini API with thinking support |

### Tools (`src/tools/`)

| Module | Purpose |
|--------|---------|
| `base.py` | Abstract BaseTool class with pause/resume support |
| `checkpoint.py` | Checkpoint persistence for interrupted batch processing |
| `config.py` | Tools configuration loader with on-demand creation |
| `defaults.py` | Default settings and prompts for tools |
| `file_handler.py` | File type detection, directory scanning, API message building |
| `file_processor.py` | File Processor tool - batch process images/text/code with AI |

## Tools Configuration

The `tools_config.json` file (auto-created on demand) contains:
- Tool prompts (OCR, Describe, Summarize, Code Review, etc.)
- Output modes (individual files or combined)
- File type mappings for auto-detection
- Settings (delay between requests, checkpoint options)

Access via terminal: Press `[X]` → `[1] File Processor`