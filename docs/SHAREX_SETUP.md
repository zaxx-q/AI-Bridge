# ShareX Integration Guide

This guide explains how to set up ShareX to work with AI Bridge for image processing tasks like OCR, translation, and description.

> **Note**: Screenshots can be added to this guide. Place them in `docs/images/` and reference them below.

## Prerequisites

- [ShareX](https://getsharex.com/) installed
- AI Bridge running (`python main.py`)

## Step 1: Create Custom Uploader

1. Open ShareX
2. Go to **Destinations** → **Custom uploader settings**
3. Click **New** to create a new uploader

![Custom uploader settings](images/sharex-1-new-uploader.png)

## Step 2: Configure the Uploader

Fill in the following settings:

| Setting | Value |
|---------|-------|
| **Name** | `AI Bridge - OCR` (or any name) |
| **Destination type** | `Image uploader` |
| **Method** | `POST` |
| **Request URL** | `http://127.0.0.1:5000/ocr` |
| **Body** | `Form data (multipart/form-data)` |
| **File form name** | `image` |

![Uploader configuration](images/sharex-2-config.png)

### Available Endpoints

Choose the endpoint based on your use case:

| Endpoint | Purpose |
|----------|---------|
| `/ocr` | Extract text from image |
| `/ocr_translate` | Extract and translate text |
| `/describe` | Describe image content |
| `/code` | Extract and format code from image |

### Query Parameters

Add these to the URL for additional behavior:

| Parameter | Values | Effect |
|-----------|--------|--------|
| `?show=yes` | `yes`, `no` | Open result in chat window |
| `?lang=XX` | Language code | Target language for translation |

**Examples:**
- `http://127.0.0.1:5000/ocr?show=yes` - OCR with chat follow-up
- `http://127.0.0.1:5000/ocr_translate?lang=en` - Translate to English

## Step 3: Configure Response

In the **Response** section:

1. Set **URL** field to: `{response}`

This copies the extracted text directly to your clipboard.

![Response configuration](images/sharex-3-response.png)

## Step 4: Create Hotkey Workflow

1. Go to **Hotkey settings** (or right-click tray → Hotkey settings)
2. Click **Add...** to create a new hotkey
3. Set:
   - **Task**: `Capture region` (or `Capture active window`, etc.)
   - **Hotkey**: Your preferred key combination

![Hotkey setup](images/sharex-4-hotkey.png)

## Step 5: Configure Task Settings

1. Click the **Gear icon** ⚙️ next to your new hotkey
2. Configure **Override destinations**:
   - Check **Image uploader**
   - Select **Custom image uploader**
3. Configure **Override default custom uploader**:
   - Check and select your `AI Bridge - OCR` uploader
4. Configure **Override after capture tasks**:
   - Check **Upload image to host**
5. Configure **Override after upload tasks**:
   - Check **Copy URL to clipboard**

![Task settings](images/sharex-5-task-settings.png)

## Usage

1. Press your configured hotkey
2. Select a region on screen (or capture window/fullscreen)
3. Wait for AI Bridge to process the image
4. The extracted text is now in your clipboard - paste anywhere!

### Quick Access via Tray

You can also access workflows by:
1. Right-click ShareX tray icon
2. Go to **Workflows**
3. Select your workflow

## Troubleshooting

### "Connection refused" Error

- Make sure AI Bridge is running (`python main.py`)
- Check the port matches your config (default: 5000)

### Empty Response

- Check AI Bridge console for errors
- Verify your API keys are configured in `config.ini`

### Slow Processing

- Use a faster model (e.g., `gpt-oss-120b` or `gemma-3-27b-it`)
- Disable thinking mode if enabled

## Multiple Workflows

Create multiple custom uploaders for different tasks:

| Workflow | URL | Use Case |
|----------|-----|----------|
| Quick OCR | `/ocr` | Fast text extraction |
| OCR + Chat | `/ocr?show=yes` | Text with follow-up |
| Translate | `/ocr_translate?lang=en` | Foreign text |
| Describe | `/describe?show=yes` | Image description |
| Code | `/code` | Screenshot to code |

## Tips

- Use `?show=yes` when you want to ask follow-up questions about the image
- Create separate hotkeys for different workflows (e.g., `Ctrl+1` for OCR, `Ctrl+2` for translate)
- The response is plain text - it works with any application that accepts paste