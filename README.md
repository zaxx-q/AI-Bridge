# AI Bridge

**AI Bridge** is a versatile multi-modal AI assistant server that bridges the gap between your operating system and powerful AI models. It features hotkey-triggered text editing, image processing (via ShareX integration), and interactive chat assistance, all accessible through a lightweight local server and native GUI.

## Features

*   **⚡ ShareX Integration**: seamless image processing endpoints (OCR, translation, summarization) compatible with ShareX custom uploaders.
*   **⌨️ TextEditTool**: Global hotkey (default: `Ctrl+Space`) to invoke AI on selected text in *any* application.
    *   **Proofread/Rewrite**: Instant text improvement.
    *   **Replace or Chat**: Choose to replace text in-place or open a chat window.
    *   **Streaming Typing**: Simulates natural typing for direct text insertion.
*   **🖥️ Native GUI**: Lightweight, threaded Tkinter-based interface for chat sessions and history browsing.
*   **🧠 Advanced AI Features**:
    *   **Streaming**: Real-time text generation.
    *   **Thinking/Reasoning**: Support for reasoning models (e.g., Gemini 2.0 Flash Thinking) with collapsible thought process display.
    *   **Multi-Provider**: Built-in support for Google Gemini, OpenRouter, and custom OpenAI-compatible endpoints.
*   **🛡️ Robust Architecture**:
    *   **Smart Key Rotation**: Automatically rotates API keys on rate limits.
    *   **Session Management**: Auto-saves chat history to JSON.
    *   **Terminal Control**: Interactive terminal commands for server management.

## Project Structure

The project follows a modular architecture separating the web server, GUI, and AI providers:

```
AI-Bridge/
├── main.py                     # Main entry point
├── requirements.txt            # Python dependencies
├── config.ini                  # Configuration (auto-generated on first run)
├── chat_sessions.json          # Saved chat sessions
├── text_edit_tool_options.json # TextEditTool prompts configuration
└── src/
    ├── config.py               # Configuration management
    ├── web_server.py           # Flask web server and API endpoints
    ├── request_pipeline.py     # Unified request processing pipeline
    ├── session_manager.py      # Session persistence
    ├── terminal.py             # Interactive terminal commands
    ├── gui/                    # GUI Package (Tkinter)
    │   ├── core.py             # GUI threading and initialization
    │   ├── windows.py          # Chat and Browser windows
    │   ├── text_edit_tool.py   # TextEditTool application controller
    │   ├── popups.py           # Quick action popups
    │   └── hotkey.py           # Global hotkey listener
    └── providers/              # AI Provider Implementations
        ├── base.py             # Abstract base provider & retry logic
        ├── gemini_native.py    # Google Gemini native API
        └── openai_compatible.py # OpenRouter & Custom endpoints
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
*   `L` - List saved sessions
*   `O` - Open session browser GUI
*   `G` - Show GUI status
*   `M` - List available models
*   `T` - Toggle thinking/reasoning mode
*   `R` - Toggle streaming mode
*   `H` - Help menu
*   `Ctrl+C` - Shutdown

### TextEditTool (Global Hotkey)
1.  Select text in any application (Notepad, Browser, IDE, etc.).
2.  Press **Ctrl+Space** (configurable).
3.  A popup will appear offering options like "Proofread", "Summarize", or "Custom".
4.  **Without selection**: Pressing the hotkey opens a quick input bar for asking the AI a question directly.

### ShareX Integration
Configure ShareX to send images to these endpoints (POST request with image file):
*   `http://localhost:5000/ocr`
*   `http://localhost:5000/describe`
*   `http://localhost:5000/code`

Add `?show=yes` to the URL to force the result to open in a chat window instead of just returning text.

## Configuration Options

The `config.ini` file allows extensive customization:

*   **Providers**: Switch between `google`, `openrouter`, or `custom`.
*   **Models**: Set specific models (e.g., `gemini-2.0-flash`, `gpt-4o`).
*   **Streaming**: Enable/disable `streaming_enabled`.
*   **Thinking**: Enable `thinking_enabled` to see the AI's reasoning process (for supported models).
*   **TextEditTool**: Customize the `text_edit_tool_hotkey` and `text_edit_tool_response_mode`.

## License

[MIT License](LICENSE)
