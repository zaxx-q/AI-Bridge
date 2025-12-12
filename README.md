# AI Bridge

<p align="center">
  <strong>v1.0.0</strong> • Windows Desktop AI Assistant
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
- **Translation** - Translate foreign text
- **Code extraction** - Convert code screenshots to text
- **Description** - Get AI descriptions of images

Results copy to clipboard automatically. See [ShareX Setup Guide](docs/SHAREX_SETUP.md).

### 💬 Chat Interface
Modern chat windows with:
- Streaming responses (real-time typing)
- Markdown rendering
- Session history (browse and restore)
- Catppuccin-themed UI

### 🔄 Robust Backend
- **Multi-provider support** - Google Gemini, OpenRouter, custom endpoints
- **Automatic key rotation** - Switch API keys on rate limits
- **Smart retry logic** - Handles errors gracefully
- **Streaming support** - Real-time responses

## 🚀 Quick Start

### Installation

```bash
git clone https://github.com/yourusername/AI-Bridge.git
cd AI-Bridge
pip install -r requirements.txt
```

### First Run

```bash
python main.py
```

On first run, AI Bridge creates `config.ini` and exits. Edit this file to add your API keys:

```ini
[google]
AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

[openrouter]
sk-or-v1-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

### Run Again

```bash
python main.py
```

The app starts minimized to system tray. The console hides automatically.

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
[settings]
default_provider = google
google_model = gemini-2.5-flash
```

Available providers:
- `google` - Native Gemini API (recommended)
- `openrouter` - OpenRouter.ai models
- `custom` - Any OpenAI-compatible endpoint

### TextEditTool Options

Customize prompts in `text_edit_tool_options.json`:

```json
{
  "prompts": {
    "proofread": "Proofread and correct this text...",
    "rewrite": "Rewrite this text to be clearer..."
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

## 🔧 Command Line Options

```bash
python main.py                  # Normal start (tray mode, console hidden)
python main.py --no-tray        # No tray icon, console stays visible
python main.py --show-console   # Tray mode but keep console visible
```

## 📖 Documentation

- [Project Structure](docs/PROJECT_STRUCTURE.md) - File organization
- [Architecture](docs/ARCHITECTURE.md) - Technical details
- [ShareX Setup](docs/SHAREX_SETUP.md) - Screenshot integration

## 🗺️ Roadmap

- [ ] **Localization** - Multi-language support for UI
- [ ] **Prompt Editor** - GUI for editing text_edit_tool_options.json
- [ ] **Colored Emoji** - Proper emoji rendering in console, chat, and popups

## 📝 Requirements

- **Windows 10/11** (uses Windows-specific APIs for tray and console)
- **Python 3.14+**
- API keys for at least one provider (Google Gemini recommended)

## 📄 License

[MIT License](LICENSE)

---

<p align="center">
  Made with ❤️ for productivity
</p>
