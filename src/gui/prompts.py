#!/usr/bin/env python3
"""
Unified prompt configuration loader.

Loads prompts.json which contains:
- text_edit_tool: Text manipulation prompts (migrated from text_edit_tool_options.json)
- snip_tool: Image analysis prompts (new)
- endpoints: Flask API endpoint prompts (optional, disabled by default)

This module replaces direct loading from text_edit_tool_options.json and
provides a unified interface for all prompt types.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

PROMPTS_FILE = "prompts.json"

# =============================================================================
# Default Snip Tool Configuration
# =============================================================================

DEFAULT_SNIP_SETTINGS = {
    "system_instruction": "You are an AI assistant specialized in analyzing images.",
    "popup_groups": [
        {"name": "Analysis", "items": ["Describe", "Summarize", "Extract Text"]},
        {"name": "Code", "items": ["Explain Code", "Debug", "Convert"]},
        {"name": "Data", "items": ["Extract Data", "Transcribe"]}
    ],
    "custom_task_template": "Regarding this image: {custom_input}",
    "allow_text_edit_actions": True,
    "popup_items_per_page": 6
}

DEFAULT_SNIP_ACTIONS = {
    "Describe": {
        "icon": "🖼️",
        "system_prompt": "You are an image analysis expert who provides detailed, accurate descriptions.",
        "task": "Describe this image in detail. Include all visible elements, text, colors, layout, and context.",
        "show_chat_window": True
    },
    "Extract Text": {
        "icon": "📄",
        "system_prompt": "You are an OCR specialist who extracts text with high accuracy.",
        "task": "Extract all text from this image. Preserve the original formatting, line breaks, and layout as closely as possible.",
        "show_chat_window": True
    },
    "Explain Code": {
        "icon": "💻",
        "system_prompt": "You are a code analysis expert who explains code clearly and concisely.",
        "task": "Analyze the code in this screenshot. Explain what it does, its purpose, and any notable patterns or techniques used.",
        "show_chat_window": True
    },
    "Debug": {
        "icon": "🐛",
        "system_prompt": "You are a debugging expert who identifies issues in code with precision.",
        "task": "Examine this code screenshot carefully. Identify any bugs, errors, potential issues, anti-patterns, or improvements. Be specific about line numbers or locations if visible.",
        "show_chat_window": True
    },
    "Extract Data": {
        "icon": "📊",
        "system_prompt": "You are a data extraction specialist who structures information accurately.",
        "task": "Extract any structured data from this image (tables, lists, key-value pairs, forms). Format it clearly using Markdown.",
        "show_chat_window": True
    },
    "Summarize": {
        "icon": "📝",
        "system_prompt": "You are a summarization expert who distills information to its essence.",
        "task": "Summarize the key information visible in this image concisely. Focus on the most important points.",
        "show_chat_window": True
    },
    "Transcribe": {
        "icon": "✍️",
        "system_prompt": "You are a transcription specialist for handwritten text and documents.",
        "task": "Transcribe any handwritten or printed text in this image as accurately as possible. Note any unclear parts.",
        "show_chat_window": True
    },
    "Convert": {
        "icon": "🔄",
        "system_prompt": "You are a code formatting specialist who produces clean, idiomatic code.",
        "task": "Convert the code in this screenshot to clean, well-formatted code. Fix any obvious issues and follow best practices.",
        "show_chat_window": True
    },
    "_Custom": {
        "icon": "⚡",
        "system_prompt": "You are a versatile image analysis assistant who adapts to any request.",
        "task": "",
        "show_chat_window": True
    }
}

# =============================================================================
# Default Endpoints Configuration
# =============================================================================

DEFAULT_ENDPOINTS_SETTINGS = {
    "enabled": False,
    "description": "Flask API endpoints for external tools like ShareX. Disabled by default - use built-in screen snipping instead."
}

DEFAULT_ENDPOINTS = {
    "ocr": "Extract all text from this image. Return ONLY the extracted text, preserving formatting.",
    "translate": "Translate all text visible in this image to English. Return only the translated text.",
    "summarize": "Summarize the content shown in this image. Be concise but comprehensive."
}


class PromptsConfig:
    """
    Unified prompts configuration manager.
    
    Provides access to:
    - text_edit_tool: Text manipulation prompts
    - snip_tool: Image analysis prompts
    - endpoints: Flask API endpoint prompts
    
    Usage:
        prompts = PromptsConfig.get_instance()
        snip_actions = prompts.get_snip_actions()
        text_actions = prompts.get_text_edit_actions()
    """
    
    _instance = None
    
    @classmethod
    def get_instance(cls) -> 'PromptsConfig':
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        """Reset singleton (useful for testing)."""
        cls._instance = None
    
    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._file_path = Path(PROMPTS_FILE)
        self._load()
    
    def _load(self):
        """Load prompts from JSON file or use defaults."""
        if self._file_path.exists():
            try:
                with open(self._file_path, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                logging.debug(f'Loaded prompts from {self._file_path}')
                
                # Ensure required sections exist
                self._ensure_sections()
                
            except Exception as e:
                logging.error(f'Failed to load prompts.json: {e}')
                self._config = self._get_defaults()
        else:
            logging.debug('prompts.json not found, using defaults')
            self._config = self._get_defaults()
            self._save()
    
    def _ensure_sections(self):
        """Ensure all required sections exist with defaults."""
        changed = False
        
        if "text_edit_tool" not in self._config:
            self._config["text_edit_tool"] = self._get_text_edit_defaults()
            changed = True
        
        if "snip_tool" not in self._config:
            self._config["snip_tool"] = {
                "_settings": DEFAULT_SNIP_SETTINGS,
                **DEFAULT_SNIP_ACTIONS
            }
            changed = True
        
        if "endpoints" not in self._config:
            self._config["endpoints"] = {
                "_settings": DEFAULT_ENDPOINTS_SETTINGS,
                **DEFAULT_ENDPOINTS
            }
            changed = True
        
        if changed:
            self._save()
    
    def _get_text_edit_defaults(self) -> dict:
        """Get text edit tool defaults from options.py."""
        from .options import DEFAULT_SETTINGS, DEFAULT_OPTIONS
        return {
            "_settings": DEFAULT_SETTINGS,
            **DEFAULT_OPTIONS
        }
    
    def _get_defaults(self) -> dict:
        """Get complete default configuration."""
        return {
            "_global_settings": {
                "version": 1,
                "description": "Unified prompt configuration for AIPromptBridge"
            },
            "text_edit_tool": self._get_text_edit_defaults(),
            "snip_tool": {
                "_settings": DEFAULT_SNIP_SETTINGS,
                **DEFAULT_SNIP_ACTIONS
            },
            "endpoints": {
                "_settings": DEFAULT_ENDPOINTS_SETTINGS,
                **DEFAULT_ENDPOINTS
            }
        }
    
    def _save(self):
        """Save current config to file."""
        try:
            with open(self._file_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            logging.debug(f'Saved prompts to {self._file_path}')
        except Exception as e:
            logging.error(f'Failed to save prompts.json: {e}')
    
    def reload(self):
        """Reload configuration from file."""
        self._load()
        logging.info('Prompts configuration reloaded')
    
    # =========================================================================
    # Text Edit Tool Accessors
    # =========================================================================
    
    def get_text_edit_tool(self) -> dict:
        """Get complete text edit tool configuration (including _settings)."""
        return self._config.get("text_edit_tool", {})
    
    def get_text_edit_setting(self, key: str, default=None):
        """Get a setting from text edit tool _settings."""
        tet = self.get_text_edit_tool()
        settings = tet.get("_settings", {})
        return settings.get(key, default)
    
    def get_text_edit_actions(self) -> dict:
        """Get text edit tool actions (excluding _settings)."""
        tet = self.get_text_edit_tool()
        return {k: v for k, v in tet.items() if k != "_settings"}
    
    # =========================================================================
    # Snip Tool Accessors
    # =========================================================================
    
    def get_snip_tool(self) -> dict:
        """Get complete snip tool configuration (including _settings)."""
        return self._config.get("snip_tool", {})
    
    def get_snip_setting(self, key: str, default=None):
        """Get a setting from snip tool _settings."""
        snip = self.get_snip_tool()
        settings = snip.get("_settings", {})
        return settings.get(key, DEFAULT_SNIP_SETTINGS.get(key, default))
    
    def get_snip_actions(self) -> dict:
        """Get snip tool actions (excluding _settings)."""
        snip = self.get_snip_tool()
        return {k: v for k, v in snip.items() if k != "_settings"}
    
    def can_use_text_edit_actions(self) -> bool:
        """Check if snip tool can borrow text edit tool actions."""
        return self.get_snip_setting("allow_text_edit_actions", True)
    
    # =========================================================================
    # Endpoints Accessors
    # =========================================================================
    
    def get_endpoints(self) -> dict:
        """Get complete endpoints configuration (including _settings)."""
        return self._config.get("endpoints", {})
    
    def get_endpoint_prompts(self) -> dict:
        """Get endpoint prompts (excluding _settings)."""
        endpoints = self.get_endpoints()
        return {k: v for k, v in endpoints.items() if k != "_settings"}
    
    def are_endpoints_enabled(self) -> bool:
        """Check if Flask endpoints are enabled."""
        endpoints = self.get_endpoints()
        settings = endpoints.get("_settings", {})
        return settings.get("enabled", False)
    
    # =========================================================================
    # Migration Support
    # =========================================================================
    
    def migrate_from_legacy(self, legacy_options_path: str = "text_edit_tool_options.json"):
        """
        Migrate from legacy text_edit_tool_options.json to unified prompts.json.
        
        This is called once during upgrade to preserve user customizations.
        """
        legacy_path = Path(legacy_options_path)
        if not legacy_path.exists():
            logging.debug('No legacy options file to migrate')
            return False
        
        try:
            with open(legacy_path, 'r', encoding='utf-8') as f:
                legacy_options = json.load(f)
            
            # Update text_edit_tool section with legacy content
            self._config["text_edit_tool"] = legacy_options
            self._save()
            
            logging.info(f'Migrated {legacy_options_path} to prompts.json')
            return True
            
        except Exception as e:
            logging.error(f'Failed to migrate legacy options: {e}')
            return False


# =============================================================================
# Convenience Functions
# =============================================================================

def get_prompts_config() -> PromptsConfig:
    """Get the prompts configuration instance."""
    return PromptsConfig.get_instance()


def reload_prompts():
    """Reload prompts configuration from file."""
    PromptsConfig.get_instance().reload()