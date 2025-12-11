# AI Bridge

**AI Bridge** is a versatile multi-modal AI assistant server that bridges the gap between your operating system and powerful AI models. It features hotkey-triggered text editing, image processing (via ShareX integration), and interactive chat assistance, all accessible through a lightweight local server and native GUI.

## Features

*   **⚡ ShareX Integration**: Seamless image processing endpoints (OCR, translation, summarization) compatible with ShareX custom uploaders.
*   **⌨️ TextEditTool**: Global hotkey (default: `Ctrl+Space`) to invoke AI on selected text in *any* application.
    *   **Proofread/Rewrite**: Instant text improvement.
    *   **Replace or Chat**: Choose to replace text in-place or open a chat window.
    *   **Streaming Typing**: Simulates natural typing for direct text insertion.
*   **🖥️ Modern Native GUI**: Tkinter-based interface with Catppuccin theme, thread-safe window management via GUICoordinator.
    *   **Chat Windows**: Interactive sessions with markdown rendering.
    *   **Session Browser**: Browse and restore chat history.
    *   **Modern UI Components**: Segmented toggles, carousel buttons, tooltips.
*   **🧠 Advanced AI Features**:
    *   **Streaming**: Real-time text generation with buffered typing.
    *   **Thinking/Reasoning**: Provider-specific thinking configuration.
    *   **Multi-Provider**: Unified provider abstraction for Google Gemini (Native), OpenRouter, and custom OpenAI-compatible endpoints.
*   **🛡️ Robust Architecture**:
    *   **Request Pipeline**: Unified request processing with consistent logging and token tracking.
    *   **Smart Key Rotation**: Automatic key rotation on rate limits with exhaustion detection.
    *   **Session Management**: Sequential session IDs with auto-save to JSON.
    *   **Terminal Control**: Interactive terminal commands for server management.

## Project Structure

The project follows a modular architecture separating the web server, GUI, and AI providers:

```
AI-Bridge/
├── main.py                     # Main entry point
├── requirements.txt            # Python dependencies
├── config.ini                  # Configuration (auto-generated on first run)
├── chat_sessions.json          # Saved chat sessions
├── text_edit_tool_options.json # TextEditTool prompts/settings
├── LICENSE
├── README.md
├── AGENTS.md                   # AI agent guidance (not in git)
└── src/
    ├── __init__.py
    ├── api_client.py           # Unified API interface using providers
    ├── config.py               # Custom INI parser, configuration management
    ├── key_manager.py          # API key rotation with exhaustion tracking
    ├── request_pipeline.py     # Unified request processing with logging
    ├── session_manager.py      # Session persistence with sequential IDs
    ├── terminal.py             # Interactive terminal commands
    ├── utils.py                # Utility functions (strip_markdown, etc.)
    ├── web_server.py           # Flask server and API endpoints
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
    └── providers/              # AI Provider Implementations
        ├── __init__.py         # Provider exports and factory
        ├── base.py             # Abstract base provider, retry logic, ProviderResult
        ├── gemini_native.py    # Native Gemini API with full feature support
        └── openai_compatible.py # OpenRouter, Custom, Google OpenAI-compat
```

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yourusername/AI-Bridge.git
    cd AI-Bridge
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **First Run (Generate Config):**
    Run the server once to generate the default configuration file.
    ```bash
    python main.py
    ```
    The server will create `config.ini` and exit or prompt you to configure it.

4.  **Configuration:**
    Edit `config.ini` and add your API keys:
    ```ini
    [google]
    # Add your Gemini API keys here
    AIzaSy...

    [openrouter]
    # Add OpenRouter keys here
    sk-or-v1...
    ```

## Usage

### Starting the Server

```bash
python main.py
```
The server starts at `http://127.0.0.1:5000` by default.

### Terminal Commands
While the server is running, you can use these keyboard commands in the terminal:

| Key | Command | Description |
|-----|---------|-------------|
| `L` | Sessions | List saved sessions |
| `O` | Browser | Open session browser GUI |
| `E` | Endpoints | List registered API endpoints |
| `M` | Models | List available models from API |
| `P` | Provider | Switch API provider |
| `S` | Status | Show comprehensive system status |
| `T` | Thinking | Toggle thinking/reasoning mode |
| `R` | Streaming | Toggle streaming mode |
| `V` | View | View a session by ID |
| `D` | Delete | Delete a session by ID |
| `C` | Clear | Clear all sessions |
| `H` | Help | Show help menu |
| `Ctrl+C` | Shutdown | Shutdown server |

### TextEditTool (Global Hotkey)
1.  Select text in any application (Notepad, Browser, IDE, etc.).
2.  Press **Ctrl+Space** (configurable).
3.  A popup will appear offering options like "Proofread", "Summarize", or "Custom".
4.  **Without selection**: Pressing the hotkey opens a quick input bar for asking the AI a question directly.

### ShareX Integration

To set up ShareX as an OCR/image processing tool:

1.  **Create Custom Uploader**: Go to `Custom uploader settings → New`.
2.  **Configure Request**:
    *   **Name**: `OCR` (or any name)
    *   **Destination type**: `Image uploader`
    *   **Method**: `POST`
    *   **Request URL**: `http://127.0.0.1:5000/ocr` (or `/describe`, `/code`, etc.)
    *   **Body**: `Form data (multipart/form-data)`
    *   **File form name**: `image` (Required)
3.  **Configure Response**: Set the **URL** field to `{response}`.
4.  **Create Workflow/Hotkey**:
    *   Go to `Hotkey settings → Add...`
    *   Task: `Capture region` (or any other capture methods)
    *   Hotkey: Set to any
    *   Click the **Gear icon** (Task settings) for this hotkey:
        *   **Override after capture tasks**: Check `Upload image to host`.
        *   **Override after upload tasks**: Check `Copy URL to clipboard`.
        *   **Override destinations**: Check `Image uploader` → Select `Custom image uploader`.
        *   **Override default custom uploader**: Check and select your `OCR` custom uploader.

**Usage**: Press your hotkey, select a region, and the extracted text will be copied to your clipboard automatically. You can also activate by right clicking tray → Workflows → Select workflow

> 💡 **Tip**: Add `?show=yes` to the URL to open results in a chat window for follow-up questions.

## Configuration Options

The `config.ini` file allows extensive customization:

*   **Providers**: Switch between `google`, `openrouter`, or `custom`.
*   **Models**: Set specific models (e.g., `gemini-2.0-flash`, `gpt-4o`).
*   **Streaming**: Enable/disable with `streaming_enabled`.
*   **Thinking**: Enable with `thinking_enabled` to see the AI's reasoning process.
*   **TextEditTool**: Customize `text_edit_tool_hotkey` and `text_edit_tool_response_mode`.

### Thinking Configuration per Provider

Different providers have different thinking/reasoning configurations:

| Provider | Config Key | Values | Description |
|----------|-----------|--------|-------------|
| OpenAI-compatible | `reasoning_effort` | `low`, `medium`, `high` | Reasoning effort level |
| Gemini 2.5 | `thinking_budget` | integer (`-1` = auto) | Token budget for thinking |
| Gemini 3.x | `thinking_level` | `low`, `high` | Thinking level |

**Note**: The configuration parser supports multiline values with `\` continuation.

## Architecture

### Provider System

All API calls flow through the unified provider system in `src/providers/`:

- **BaseProvider**: Abstract base class with common retry logic and `ProviderResult` dataclass
- **OpenAICompatibleProvider**: Handles Custom endpoints, OpenRouter, and Google OpenAI-compatible
- **GeminiNativeProvider**: Native Gemini API with full feature support (thinking, tools, etc.)

Use `get_provider_for_type()` from `src/api_client.py` to get the appropriate provider.

### Request Pipeline

All AI requests flow through `RequestPipeline` in `src/request_pipeline.py`:

- Consistent console logging for ALL requests
- Token usage tracking
- Origin tracking (CHAT_WINDOW, POPUP_INPUT, ENDPOINT_OCR, etc.)

### GUI Threading Model

The GUI uses `GUICoordinator` singleton in `src/gui/core.py`:

- Single `tk.Tk()` root with queue-based window creation
- All windows created as `tk.Toplevel` children
- Thread-safe window creation via request queue
- Standalone windows use polling loop instead of `mainloop()`

### Key Rotation

`KeyManager` in `src/key_manager.py` handles automatic key rotation:

- Rotates on 429 (rate limit), 401/402/403 (auth errors)
- Tracks exhausted keys to avoid re-trying
- Configurable delays based on error type

## Known Issues & Limitations

As this project is in active development, please be aware:
- Some edge cases in TextEditTool text replacement may not work perfectly across all applications
- Not all AI models support thinking/reasoning mode
- pynput keyboard typing needs 5ms delay per character for Unicode stability

## Contributing

Contributions are welcome! If you encounter bugs or have feature suggestions:
1. Check existing issues on GitHub
2. Open a new issue with detailed information
3. Pull requests for bug fixes are appreciated

## Roadmap

- [ ] Improve error handling and user feedback
- [ ] Add more TextEditTool preset options
- [ ] Support for additional AI providers
- [ ] Better session management UI
- [ ] Comprehensive testing suite

## License

[MIT License](LICENSE)
