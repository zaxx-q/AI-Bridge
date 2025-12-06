# AI Bridge

**AI Bridge** - A versatile multi-modal AI assistant server supporting hotkey-triggered text editing, image processing, and AI assistance through customizable APIs with Dear PyGui interface.

## Project Structure

The project has been refactored into a clean, modular structure:

```
AI-Bridge/
├── main.py                 # Main entry point
├── requirements.txt        # Python dependencies
├── config.ini             # Configuration file (created on first run)
├── chat_sessions.json     # Saved chat sessions (auto-created)
├── text_edit_tool_options.json  # TextEditTool prompts configuration
└── src/                   # Source code package
    ├── __init__.py
    ├── config.py          # Configuration loading and defaults
    ├── utils.py           # Text processing and error detection utilities
    ├── key_manager.py     # API key rotation and management
    ├── session_manager.py # Chat session persistence
    ├── api_client.py      # API calling with retry logic
    ├── terminal.py        # Interactive terminal commands
    ├── web_server.py      # Flask web server and routes
    ├── text_edit_tool/    # TextEditTool module (hotkey text processing)
    │   ├── __init__.py
    │   ├── app.py         # Main controller
    │   ├── hotkey_listener.py
    │   ├── text_handler.py
    │   ├── popup_window.py
    │   ├── response_window.py
    │   ├── ai_client.py
    │   └── options.py
    └── gui/               # GUI components (Dear PyGui)
        ├── __init__.py
        ├── core.py        # GUI initialization and threading
        ├── utils.py       # Clipboard and markdown rendering
        └── windows.py     # Window creation (Result, Chat, Browser)
```

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   # or with uv:
   uv pip install -r requirements.txt
   ```

2. Run the server for the first time to generate `config.ini`:
   ```bash
   python main.py
   # or with uv:
   uv run python main.py
   ```

3. Edit `config.ini` and add your API keys

4. Run the server again:
   ```bash
   python main.py
   ```

## Usage

### Starting the Server

```bash
python main.py
```

The server will start at `http://127.0.0.1:5000` by default.

### ShareX Image Processing

All endpoints accept POST requests with an image:

- `/ocr` - Extract text from image
- `/translate` - Translate text to English
- `/summarize` - Summarize image content
- `/describe` - Describe image in detail
- `/code` - Extract code from image
- `/textedit` - Logical endpoint used by TextEditTool sessions
- And more... (customizable in config.ini)

#### Show Modes

Add `?show=<mode>` to any endpoint:

- `?show=no` - Return text only (default)
- `?show=yes` - Display result in chat GUI window
- Note: Older `gui`/`chatgui` values are deprecated.

Example:
```
POST http://127.0.0.1:5000/ocr?show=chatgui
```

### TextEditTool (Hotkey Text Processing)

Press **Ctrl+Space** (configurable) to activate:

- **With text selected**: Shows prompt options (Proofread, Rewrite, Summarize, etc.)
- **Without text selected**: Opens direct AI chat

Configure in `config.ini`:
```ini
text_edit_tool_enabled = true
text_edit_tool_hotkey = ctrl+space
# Response mode is now selected via popup radio buttons (Default/Replace/Show)
```

### Terminal Commands

While the server is running, press these keys:

- `L` - List saved sessions
- `O` - Open session browser GUI
- `S` - Show session details
- `D` - Delete a session
- `C` - Clear all sessions
- `G` - Show GUI status
- `M` - Model management (list available models)
- `T` - Toggle thinking/reasoning mode
- `R` - Toggle streaming mode
- `H` - Help

### API Routes

- `GET /` - Service information
- `GET /health` - Health check
- `GET /sessions` - List all sessions
- `GET /sessions/<id>` - Get session details
- `GET /gui/browser` - Open session browser GUI
- `GET /models` - List available models (dynamically fetched from API)

## Configuration

Edit `config.ini` to customize:

- Server host and port
- Default provider (google, openrouter, custom)
- API models (dynamically selectable via GUI dropdown)
- Retry settings
- AI parameters (temperature, max_tokens, etc.)
- Custom endpoints
- TextEditTool settings (hotkey, response mode)
- **Streaming**: `streaming_enabled = true/false`
- **Thinking/Reasoning**: `thinking_enabled = true/false`, `thinking_output = reasoning_content`

## Features

✅ **ShareX Integration:**
- Multiple API provider support (Google Gemini, OpenRouter, Custom)
- Smart API key rotation on rate limits
- Automatic retry with exponential backoff
- Chat sessions with history
- GUI windows for results and interactive chat
- Configurable endpoints
- Provider/model override via query params or headers

✅ **Streaming Support:**
- Real-time SSE streaming for all providers (Google, OpenRouter, Custom)
- Streaming to chat window with live updates
- Streaming to active text field (replace mode) with rate-limited typing
- Toggle via terminal `[R]` or config `streaming_enabled`

✅ **Model Selection:**
- Dynamic model fetching from APIs (Google, OpenRouter, Custom)
- GUI dropdown for model selection in chat windows
- Model changes persist to config.ini and chat_sessions.json
- Terminal `[M]` command to list all available models

✅ **Thinking/Reasoning Mode:**
- Support for `reasoning_content` in API responses
- Collapsible thinking display in chat windows
- Toggle via terminal `[T]` or config `thinking_enabled`

✅ **TextEditTool:**
- Global hotkey activation (Ctrl+Space by default)
- Text selection-based prompts
- AI chat without selection
- Replace or popup response modes
- Streaming to active field (default_show=no)
- Customizable prompts
- Dark/light mode support

✅ **Clean Architecture:**
- Modular structure for easier maintenance
- Clear separation of concerns
- Better testability
- Easier to extend with new features

## License

Same as original project.
