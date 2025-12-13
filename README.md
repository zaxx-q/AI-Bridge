# AI Bridge

<p align="center">
  <strong>• Windows Desktop AI Assistant •</strong>
</p>

**AI Bridge** is a Windows desktop application that brings AI assistance to your fingertips. Use global hotkeys to edit text in any application, process screenshots with OCR, and chat with AI models—all from a lightweight system tray app.

## ✨ Features

### 🎯 TextEditTool
Press **Ctrl+Space** anywhere to invoke AI on selected text:
- **Proofread** - Fix grammar and spelling
- **Rewrite** - Improve clarity and style  
- **Translate** - Convert to another language
- **Custom prompts** - Define your own actions

Works in any application: browsers, IDEs, Notepad, Word, everywhere.

### 📸 ShareX Integration
Process screenshots with AI:
- **OCR** - Extract text from images
- **Translation** - Translate foreign text (with dynamic `?lang=` parameter)
- **Code extraction** - Convert code screenshots to text
- **Description** - Get AI descriptions of images
- **Custom endpoints** - Create your own prompts

Results copy to clipboard automatically. See [ShareX Setup Guide](docs/SHAREX_SETUP.md).

### 💬 Chat Interface
Lightweight chat windows with:
- Streaming responses (real-time typing)
- Markdown rendering
- Session history (browse and restore)
- Catppuccin-themed UI

### 🔄 Robust Backend
- **Multi-provider support** - Google Gemini, OpenRouter, custom endpoints
- **Automatic key rotation** - Switch API keys on rate limits (429, 401, 403)
- **Smart retry logic** - Handles errors gracefully with configurable delays
- **Empty response detection** - Automatically retries with next key
- **Streaming support** - Real-time responses

## 🚀 Quick Start

### Download (Recommended)

1. Download `AIBridge.exe` from [GitHub Releases](https://github.com/zaxx-q/AI-Bridge/releases)
2. Run it - on first launch, it creates `config.ini` and exits
3. Edit `config.ini` to add your API keys
4. Run again - the app starts minimized to system tray

### From Source (Alternative)

```bash
git clone https://github.com/zaxx-q/AI-Bridge.git
cd AI-Bridge
pip install -r requirements.txt
python main.py
```

### Configuration

Edit `config.ini` to add your API keys:

```ini
[google]
AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

[openrouter]
sk-or-v1-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

> 💡 **Tip**: Add multiple keys (one per line) for automatic rotation when rate limits are hit.

## 📋 Usage

### System Tray

Right-click the tray icon for:
- **Show/Hide Console** - Toggle console visibility
- **Session Browser** - View chat history
- **Edit config.ini** - Open configuration
- **Restart** - Restart the application
- **Quit** - Exit completely

### TextEditTool

1. Select text in any application
2. Press **Ctrl+Space**
3. Choose an action (Proofread, Rewrite, etc.)
4. Text is replaced or opened in chat

**Without selection**: Opens a quick input bar for direct questions.

### API Endpoints

Access AI via HTTP POST:

```bash
# Basic OCR
curl -X POST -F "image=@screenshot.png" http://127.0.0.1:5000/ocr

# OCR with translation
curl -X POST -F "image=@screenshot.png" "http://127.0.0.1:5000/ocr_translate?lang=Japanese"

# With chat window
curl -X POST -F "image=@screenshot.png" "http://127.0.0.1:5000/describe?show=yes"
```

#### Query Parameters

| Parameter | Example | Effect |
|-----------|---------|--------|
| `?show=yes` | Open result in chat window |
| `?lang=XX` | Target language (for `ocr_translate`) |
| `?prompt=...` | Override the endpoint prompt |
| `?model=...` | Override the model |
| `?provider=...` | Override the provider |

### Console Commands

When console is visible, press these keys:

| Key | Action |
|-----|--------|
| `S` | Show system status |
| `O` | Open session browser |
| `M` | List available models |
| `P` | Switch AI provider |
| `T` | Toggle thinking mode |
| `R` | Toggle streaming mode |
| `H` | Show help |

## ⚙️ Configuration

### Providers

Set your preferred provider in `config.ini`:

```ini
[config]
default_provider = google
google_model = gemini-2.5-flash
```

Available providers:
- `google` - Native Gemini API (recommended)
- `openrouter` - OpenRouter.ai models
- `custom` - Any OpenAI-compatible endpoint

### Custom Endpoints

Add your own endpoints in `config.ini`:

```ini
[endpoints]
# Simple custom endpoint
my_analyzer = Analyze this image and list all objects found.

# Dynamic language endpoint using {lang} placeholder
my_translator = Translate to {lang}. Keep formatting.
```

Access via `http://127.0.0.1:5000/my_analyzer` or `http://127.0.0.1:5000/my_translator?lang=French`

### TextEditTool Options

Customize prompts in `text_edit_tool_options.json`:

```json
{
  "Proofread": {
    "icon": "✏",
    "system_prompt": "You are a meticulous proofreader...",
    "task": "Proofread the following text...",
    "show_chat_window_instead_of_replace": false
  },
  "Rewrite": {
    "icon": "📝",
    "system_prompt": "You are an expert editor...",
    "task": "Rewrite this text to improve clarity...",
    "show_chat_window_instead_of_replace": false
  }
}
```

## 💡 Tips

### For Faster Responses
- Use non-reasoning models (e.g., `gemini-2.0-flash` instead of `gemini-2.5-pro`)
- Disable thinking mode: Press `T` in console or set `thinking_enabled = false`
- Keep streaming enabled for perceived faster responses

### For Better Results
- Enable thinking mode for complex tasks
- Use specific prompts in TextEditTool
- Add context when asking questions

### API Key Management
- Add multiple API keys (one per line) for automatic rotation
- If one key hits rate limits, the next one is used automatically
- The system tracks exhausted keys and skips them
- Keys rotate on: 429 (rate limit), 401/402/403 (auth errors), empty responses

## 🔧 Command Line Options

```bash
AIBridge.exe                    # Normal start (tray mode, console hidden)
AIBridge.exe --no-tray          # No tray icon, console stays visible
AIBridge.exe --show-console     # Tray mode but keep console visible
```

## 📖 Documentation

- [Project Structure](docs/PROJECT_STRUCTURE.md) - File organization
- [Architecture](docs/ARCHITECTURE.md) - Technical details
- [ShareX Setup](docs/SHAREX_SETUP.md) - Screenshot integration

## 🗺️ Roadmap

- [ ] **Prompt Editor** - GUI for editing text_edit_tool_options.json
- [ ] **Colored Emoji** - Proper emoji rendering in console, chat, and popups
- [ ] **Localization** - Multi-language support for UI

## 📝 Requirements

- **Windows 10/11** (uses Windows-specific APIs for tray and console)
- **Python 3.14+** (if running from source)
- API keys for at least one provider (Google Gemini recommended)

## 📄 License

[MIT License](LICENSE)

---

<p align="center">
  Made with ❤️ for productivity
</p>
