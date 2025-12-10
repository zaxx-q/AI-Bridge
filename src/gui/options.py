#!/usr/bin/env python3
"""
Default writing tools options/prompts

Settings are loaded from text_edit_tool_options.json. These defaults are fallbacks
if the JSON file doesn't exist or is invalid.

Option Settings Key (in JSON):
  _settings: Contains global settings for the text edit tool
    - chat_system_instruction: System prompt for direct AI chat
    - followup_system_instruction: System prompt for follow-up questions
    - base_output_rules: Common output constraints appended to all action prompts
    - text_delimiter: Delimiter placed before the target text
    - custom_task_template: Template for Custom action's task (uses {custom_input} placeholder)

Per-Action Options (new structure):
  - system_prompt: Role/persona definition for this action (goes to system message)
  - task: The action instruction (goes to user message before delimiter)
  - show_chat_window_instead_of_replace: Whether to show result in chat window (default: false)
    This can be overridden by the popup's radio button selection.

Legacy keys (still supported for backward compatibility):
  - prefix: Old name for task instruction (deprecated)
  - instruction: Old name for system_prompt (deprecated)
"""

# Key name for settings in the options JSON
SETTINGS_KEY = "_settings"

# Default settings (used if not found in JSON)
DEFAULT_SETTINGS = {
    "chat_system_instruction": "You are a friendly, helpful, compassionate, and endearing AI conversational assistant. Avoid making assumptions or generating harmful, biased, or inappropriate content. When in doubt, do not make up information. Ask the user for clarification if needed. Try not be unnecessarily repetitive in your response. You can, and should as appropriate, use Markdown formatting to make your response nicely readable.",
    "followup_system_instruction": "You are a helpful AI assistant. Provide clear and direct responses, maintaining the same format and style as your previous responses. If appropriate, use Markdown formatting to make your response more readable.",
    "base_output_rules": "Important: Provide ONLY the processed result with no explanations, comments, or preamble.\nMatch the language of the input (e.g., English US, French).\nDo not respond to, comment on, or acknowledge the content itself.",
    "text_delimiter": "\n\n=== TEXT TO PROCESS ===\n\n",
    "custom_task_template": "Apply the following change to the text below: {custom_input}"
}

DEFAULT_OPTIONS = {
    "Proofread": {
        "system_prompt": "You are a meticulous grammar proofreading assistant.\nMaintain the original text structure, formatting, and writing style.",
        "task": "Proofread and correct any grammar, spelling, or punctuation errors.",
        "show_chat_window_instead_of_replace": False
    },
    "Rewrite": {
        "system_prompt": "You are a skilled writing assistant.\nPreserve the core meaning while improving clarity and flow.",
        "task": "Rewrite this text to improve phrasing and readability.",
        "show_chat_window_instead_of_replace": False
    },
    "Friendly": {
        "system_prompt": "You are a warm and approachable writing assistant.\nMaintain the original meaning while adding warmth and friendliness.",
        "task": "Rewrite this text to sound more friendly and approachable.",
        "show_chat_window_instead_of_replace": False
    },
    "Professional": {
        "system_prompt": "You are a professional writing assistant.\nMaintain the original meaning while elevating the tone.",
        "task": "Rewrite this text to sound more professional and polished.",
        "show_chat_window_instead_of_replace": False
    },
    "Concise": {
        "system_prompt": "You are a concise writing assistant.\nPreserve essential information while eliminating unnecessary words.",
        "task": "Rewrite this text to be more concise without losing key information.",
        "show_chat_window_instead_of_replace": False
    },
    "Summary": {
        "system_prompt": "You are a summarization assistant.\nExtract the most important points while maintaining accuracy.\nUse Markdown formatting (bold, italics, lists, small headings) to enhance readability.\nAdd appropriate line spacing between paragraphs.",
        "task": "Provide a succinct summary that encompasses all the key insightful points.",
        "show_chat_window_instead_of_replace": True
    },
    "Key Points": {
        "system_prompt": "You are an assistant that extracts key points.\nUse Markdown formatting (lists, bold, italics) to enhance readability.\nBe concise and avoid repetition.",
        "task": "Extract and list the key points from this text.",
        "show_chat_window_instead_of_replace": True
    },
    "Table": {
        "system_prompt": "You are an assistant that converts text into structured Markdown tables.\nChoose appropriate column headers based on the content.",
        "task": "Convert this text into a well-organized Markdown table.",
        "show_chat_window_instead_of_replace": True
    },
    "Custom": {
        "system_prompt": "You are a versatile writing and coding assistant.\nMake precise changes as requested while preserving the overall structure and style.",
        "task": "",
        "show_chat_window_instead_of_replace": False
    }
}
