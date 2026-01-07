# Architecture

This document describes the technical architecture of AI Bridge.

## Overview

AI Bridge is a Windows application consisting of:

1. **Flask Web Server** - REST API endpoints for image/text processing
2. **System Tray Application** - Background process management with `infi.systray`
3. **CustomTkinter GUI** - Modern chat windows, session browser, and popups with multi-theme support
4. **Rich Console Interface** - Modernized terminal UI with structured logging and panels
5. **TextEditTool** - Global hotkey integration with `pynput` and interactive popups
6. **AI Provider System** - Unified abstraction for multiple AI backends
7. **Theme System** - Multi-theme support with dark/light modes and system detection
8. **Settings Infrastructure** - GUI editors for config.ini and prompt options with hot-reload

## Component Diagram

```mermaid
flowchart TB
    subgraph Main["main.py"]
        Tray["System Tray<br/>(tray.py)"]
        Console["Console UI<br/>(terminal.py)"]
        Flask["Flask Server<br/>(web_server.py)"]
        TET["TextEditTool<br/>(text_edit_tool.py)"]
        Popups["Popups<br/>(popups.py)"]
        Modifiers["Scrollable ModifierBar<br/>(popups.py)"]
        TypingInd["TypingIndicator<br/>(popups.py)"]
    end
    
    subgraph Pipeline["Request Pipeline"]
        RP["request_pipeline.py<br/>• Logging<br/>• Token tracking<br/>• Origin tracking"]
    end
    
    subgraph APIClient["API Client"]
        AC["api_client.py<br/>get_provider_for_type()"]
    end
    
    subgraph Providers["Providers"]
        OAI["OpenAI-compatible<br/>Provider"]
        Gemini["Gemini Native<br/>Provider"]
        Custom["Custom<br/>Endpoint"]
    end
    
    subgraph KeyMgr["Key Manager"]
        KM["key_manager.py<br/>• Multiple keys per provider<br/>• Auto-rotation on error<br/>• Exhaustion detection<br/>• Retry with backoff"]
    end
    
    Tray --> Pipeline
    Flask --> Pipeline
    TET --> Popups
    Popups --> Modifiers
    TET --> TypingInd
    Popups --> Pipeline
    Pipeline --> APIClient
    APIClient --> OAI
    APIClient --> Gemini
    APIClient --> Custom
    OAI --> KM
    Gemini --> KM
    Custom --> KM
```

## Provider System

All AI API calls flow through the unified provider system in `src/providers/`.

### Provider Interface

```python
class BaseProvider:
    def call_api(messages, config, ai_params, key_manager) -> ProviderResult
    def call_api_streaming(messages, config, ai_params, key_manager, callback) -> ProviderResult
    def get_model_list(config, key_manager) -> List[str]
```

### Available Providers

| Provider | Class | Use Case |
| ---------- | ------- | ---------- |
| `google` | `GeminiNativeProvider` | Native Gemini API with thinking, tools |
| `openrouter` | `OpenAICompatibleProvider` | OpenRouter.ai models |
| `custom` | `OpenAICompatibleProvider` | Any OpenAI-compatible endpoint |

### Retry Logic

The provider system includes automatic retry with key rotation:

| Error | Action | Delay |
| ------- | -------- | ------- |
| 429 Rate Limit | Rotate to next key | None |
| 401/402/403 Auth | Rotate to next key | None |
| 5xx Server Error | Retry same key | 2 seconds |
| Empty Response | Rotate to next key | 2 seconds |
| Network Error | Rotate to next key | 1 second |

## GUI Threading Model

```mermaid
flowchart LR
    subgraph MainThread["Main Thread"]
        GC["GUICoordinator<br/>(singleton)"]
        Root["ctk.CTk()<br/>(single root)"]
    end
    
    subgraph Windows["Windows (CTkToplevel)"]
        Chat["ChatWindow"]
        Browser["SessionBrowser"]
        Popup["PopupWindow"]
    end
    
    subgraph OtherThreads["Other Threads"]
        Flask["Flask Thread"]
        Hotkey["Hotkey Thread"]
    end
    
    OtherThreads -->|"request_window()"| GC
    GC -->|"queue-based creation"| Root
    Root --> Chat
    Root --> Browser
    Root --> Popup
```

### Rules

1. **Single ctk.CTk() root** - Managed by `GUICoordinator` on a dedicated GUI thread.
2. **Thread-Safe Requests** - Windows are created via a thread-safe queue.
3. **CTkToplevel for Windows** - All application windows are children of the single root.
4. **Update Loop** - Standalone windows use an update-based loop to coexist with other threads.

### Window Types

| Window | Purpose |
| -------- | --------- |
| `ChatWindow` | Interactive AI chat with streaming |
| `SessionBrowserWindow` | Browse and restore saved sessions |
| `PopupWindow` | TextEditTool selection/input dialogs with dual input (Edit/Ask) and scrollable ModifierBar |
| `TypingIndicator` | Tooltip showing typing status and abort hotkey |
| `SettingsWindow` | GUI editor for config.ini with tabbed interface |
| `PromptEditorWindow` | GUI editor for text_edit_tool_options.json with Playground testing |

## Request Pipeline

All AI requests flow through `RequestPipeline` for consistent observability, utilizing `src/console.py` for rich output:

```python
pipeline = RequestPipeline(
    origin=RequestOrigin.CHAT_WINDOW,  # or POPUP_INPUT, ENDPOINT_OCR, etc.
    session_id=session.id
)
result = pipeline.execute(provider, messages, config, ai_params, key_manager)
```

### Features

- **Structured Logging**: Uses Rich panels to display request details (model, provider, status)
- **Token Tracking**: Input/Output/Total usage visualized in tables
- **Origin Context**: Clear indication of where the request originated
- **Timing**: Execution time tracking within the results panel
- **Error Handling**: Distinct red panels for failure states

## Session Management

Sessions are stored in `chat_sessions.json` with sequential IDs.

### Session Structure

```json
{
  "1": {
    "id": 1,
    "title": "First message preview...",
    "messages": [
      {"role": "user", "content": "..."},
      {"role": "assistant", "content": "..."}
    ],
    "thinking_content": "...",
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:01:00"
  }
}
```

### Context Injection

When a session is initiated from the TextEditTool (e.g., asking a question about selected text), the first message includes a context marker:
`[Task: Explain this text]`

This allows the AI to understand the context of the request even if the user asks "What did you just do?".

### Design Decision

Sessions do NOT store provider/model. This allows:

- Hot-switching providers mid-conversation
- No migration needed when changing default provider
- Current config is always used at request time

## System Tray (Windows)

The tray application (`src/tray.py`) manages:

- Console show/hide (console X button is disabled in tray mode)
- Application restart (spawns new process, exits current)
- Quick access to session browser
- Config file editing

### Console Window Behavior

| Action | Result |
| -------- | -------- |
| Click X on console | Button disabled (grayed out) |
| Tray → Hide Console | Hides console window |
| Tray → Show Console | Shows and focuses console |
| Tray → Quit | Clean shutdown |

## Console Interface (Rich)

The terminal interface (`src/terminal.py` and `src/console.py`) uses the `rich` library for modern console UI:

- **Centralized Configuration**: `src/console.py` defines the global `Console` instance and custom theme.
- **Panels & Tables**: Menus, session lists, and status screens use styled tables tailored for readability.
- **Color-Coded Logs**: Success, error, warning, and info messages have distinct styles.
- **Robust Fallback**: Automatically degrades gracefully if `rich` is missing (though it is a hard dependency).

## Thinking/Reasoning Configuration

Different providers have different thinking mechanisms:

| Provider | Config Key | Values |
| ---------- | ----------- | -------- |
| OpenAI-compatible | `reasoning_effort` | `low`, `medium`, `high` |
| Gemini 2.5 | `thinking_budget` | Integer (tokens, -1 = auto) |
| Gemini 3.x | `thinking_level` | `low`, `high` |

## Configuration System

The config parser (`src/config.py`) is a custom INI parser, NOT Python's `configparser`.

### Special Features

- Multiline values with `\` continuation
- Type coercion (bool, int, float, string)
- API keys are one per line in their section
- Comments with `#` or `;`
- `{lang}` placeholder support for dynamic language in prompts

### Example

```ini
[settings]
streaming_enabled = true
thinking_enabled = false
default_provider = google
google_model = gemini-2.5-flash

[google]
# API keys, one per line
AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
AIzaSyYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY

[endpoints]
# Use {lang} placeholder for dynamic language
ocr_translate = Extract and translate to {lang}. Return only translated text.
```

## Theme System

The theme system (`src/gui/themes.py`) provides centralized color management with multiple presets.

### Available Themes

| Theme | Description | Variants |
| ------- | ------------- | ---------- |
| `catppuccin` | Warm pastel colors | Mocha (dark), Latte (light) |
| `dracula` | Dark purple-based | Classic (dark), Pro (light) |
| `nord` | Arctic blue palette | Polar Night (dark), Snow Storm (light) |
| `gruvbox` | Retro earthy colors | Dark, Light |
| `onedark` | Atom editor theme | Dark, Light |
| `minimal` | Clean, minimal design | Dark, Light |
| `highcontrast` | Maximum readability | Dark, Light |

### Configuration

```ini
[config]
ui_theme = catppuccin
ui_theme_mode = auto  # auto, dark, light
```

### Usage

```python
from src.gui.themes import get_colors, ThemeRegistry

# Get current theme colors
colors = get_colors()
print(colors.bg, colors.fg, colors.accent)

# Get specific theme
dark_nord = ThemeRegistry.get_theme("nord", "dark")

# Check system dark mode
is_dark = ThemeRegistry.is_dark_mode()
```

### ThemeColors Dataclass

The `ThemeColors` dataclass provides standardized color names with legacy property aliases:

| Standard | Legacy Alias | Purpose |
| ---------- | -------------- | --------- |
| `bg` | `base` | Primary background |
| `fg` | `text` | Primary text |
| `accent` | `blue` | Primary accent color |
| `accent_green` | `green` | Success/positive |
| `accent_red` | `red` | Error/danger |
| `code_bg` | `mantle` | Code block background |
| `blockquote` | `subtext0` | Muted text |

## Emoji Support (Twemoji)

AI Bridge implements color emoji support for Windows using the Twemoji asset set. This is necessary because Windows Tkinter typically only renders monochrome outlines for emojis in Text widgets.

### EmojiRenderer (`src/gui/emoji_renderer.py`)

The `EmojiRenderer` class manages the loading, caching, and rendering of emoji images:

- **Asset Loading**: PNG images are loaded from `assets/emojis.zip` (Twemoji 72x72 set).
- **Caching**: Images are cached in memory as both `ImageTk.PhotoImage` (for tk.Text) and `CTkImage` (for CTk widgets).
- **Detection**: Uses the `emoji` library (if available) with a robust regex fallback to find emojis in text.
- **Normalization**: Handles Variation Selector 16 (FE0F), flag sequences (regional indicators), and ZWJ (Zero Width Joiner) sequences.

### Rendering Modes

1.  **Markdown Rendering (`src/gui/utils.py`)**:
    *   During markdown parsing, text segments are processed by `insert_with_emojis(text_widget, text, tags)`.
    *   It uses `text_widget.image_create()` to embed the PNG images directly into the flow of the rich text.

2.  **Widget Content (`src/gui/custom_widgets.py`)**:
    *   `prepare_emoji_content(text, size)` extracts leading emojis from button or label text.
    *   It returns the text (without emoji) and a `CTkImage` to be used with the `compound="left"` property.
    *   This is used by `create_emoji_button`, `create_section_header`, and `upgrade_tabview_with_icons`.

## Settings Infrastructure

### SettingsWindow

GUI editor for `config.ini` (`src/gui/settings_window.py`):

- **Tabbed Interface**: General, Provider, Streaming, TextEditTool, API Keys, Endpoints, Theme
- **Live Preview**: Theme tab shows real-time preview of color changes
- **Validation**: Port numbers, hotkey formats
- **Backup**: Creates `.bak` file before saving
- **Hot-Reload**: API keys and endpoints reload without restart

### PromptEditorWindow

GUI editor for `text_edit_tool_options.json` (`src/gui/prompt_editor.py`):

- **Actions Tab**: Edit action prompts, icons, and types
- **Settings Tab**: Edit global settings like output rules
- **Modifiers Tab**: Manage modifier buttons and injections
- **Groups Tab**: Organize actions into popup groups
- **Playground Tab**: Test actions and endpoints with live preview and image support
- **Hot-Reload**: Triggers `reload_options()` on save for immediate effect

### Access Methods

```python
# From any thread
from src.gui.settings_window import show_settings_window
from src.gui.prompt_editor import show_prompt_editor

show_settings_window()  # Opens Settings window
show_prompt_editor()    # Opens Prompt Editor
```

Both windows are accessible from the system tray menu.
