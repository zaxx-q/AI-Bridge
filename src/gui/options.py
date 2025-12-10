#!/usr/bin/env python3
"""
Default writing tools options/prompts

Settings are loaded from text_edit_tool_options.json. These defaults are fallbacks
if the JSON file doesn't exist or is invalid.

Option Settings Key (in JSON):
  _settings: Contains global settings for the text edit tool
    - chat_system_instruction: System prompt for direct AI chat
    - followup_system_instruction: System prompt for follow-up questions

Per-Action Options:
  - prefix: Text prepended to user's input
  - instruction: System instruction for this action
  - show_chat_window_instead_of_replace: Whether to show result in chat window (default: false)
    This can be overridden by the popup's radio button selection.
"""

# Key name for settings in the options JSON
SETTINGS_KEY = "_settings"

# Default settings (used if not found in JSON)
DEFAULT_SETTINGS = {
    "chat_system_instruction": "You are a friendly, helpful, compassionate, and endearing AI conversational assistant. Avoid making assumptions or generating harmful, biased, or inappropriate content. When in doubt, do not make up information. Ask the user for clarification if needed. Try not be unnecessarily repetitive in your response. You can, and should as appropriate, use Markdown formatting to make your response nicely readable.",
    "followup_system_instruction": "You are a helpful AI assistant. Provide clear and direct responses, maintaining the same format and style as your previous responses. If appropriate, use Markdown formatting to make your response more readable."
}

DEFAULT_OPTIONS = {
    "Proofread": {
        "prefix": "Proofread this:\n\n",
        "instruction": "You are a grammar proofreading assistant.\nOutput ONLY the corrected text without any additional comments.\nMaintain the original text structure and writing style.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.",
        "show_chat_window_instead_of_replace": False
    },
    "Rewrite": {
        "prefix": "Rewrite this:\n\n",
        "instruction": "You are a writing assistant.\nRewrite the text provided by the user to improve phrasing.\nOutput ONLY the rewritten text without additional comments.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.",
        "show_chat_window_instead_of_replace": False
    },
    "Friendly": {
        "prefix": "Make this more friendly:\n\n",
        "instruction": "You are a writing assistant.\nRewrite the text provided by the user to be more friendly.\nOutput ONLY the friendly text without additional comments.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.",
        "show_chat_window_instead_of_replace": False
    },
    "Professional": {
        "prefix": "Make this more professional:\n\n",
        "instruction": "You are a writing assistant.\nRewrite the text provided by the user to be more professional. Output ONLY the professional text without additional comments.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.",
        "show_chat_window_instead_of_replace": False
    },
    "Concise": {
        "prefix": "Make this more concise:\n\n",
        "instruction": "You are a writing assistant.\nRewrite the text provided by the user to be more concise.\nOutput ONLY the concise text without additional comments.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.",
        "show_chat_window_instead_of_replace": False
    },
    "Summary": {
        "prefix": "Summarize this:\n\n",
        "instruction": "You are a summarization assistant.\nProvide a succinct summary of the text provided by the user.\nThe summary should be succinct yet encompass all the key insightful points.\n\nTo make it quite legible and readable, you should use Markdown formatting (bold, italics, codeblocks...) as appropriate.\nYou should also add a little line spacing between your paragraphs as appropriate.\nAnd only if appropriate, you could also use headings (only the very small ones), lists, tables, etc.\n\nDon't be repetitive or too verbose.\nOutput ONLY the summary without additional comments.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.",
        "show_chat_window_instead_of_replace": True
    },
    "Key Points": {
        "prefix": "Extract key points from this:\n\n",
        "instruction": "You are an assistant that extracts key points from text provided by the user. Output ONLY the key points without additional comments.\n\nYou should use Markdown formatting (lists, bold, italics, codeblocks, etc.) as appropriate to make it quite legible and readable.\n\nDon't be repetitive or too verbose.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.",
        "show_chat_window_instead_of_replace": True
    },
    "Table": {
        "prefix": "Convert this into a table:\n\n",
        "instruction": "You are an assistant that converts text provided by the user into a Markdown table.\nOutput ONLY the table without additional comments.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.",
        "show_chat_window_instead_of_replace": True
    },
    "Custom": {
        "prefix": "Make this change to the following text:\n\n",
        "instruction": "You are a writing and coding assistant. You MUST make the user's described change to the text or code provided by the user. Output ONLY the appropriately modified text or code without additional comments. Respond in the same language as the input (e.g., English US, French). Do not answer or respond to the user's text content.",
        "show_chat_window_instead_of_replace": False
    }
}
