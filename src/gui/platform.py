#!/usr/bin/env python3
"""
Platform-specific GUI availability logic.
Centralizes the check for CustomTkinter availability and the force-fallback configuration.
"""

from ..config import load_config

# Load config to check for forced fallback
# We don't use web_server.CONFIG here because this module is imported 
# by web_server imports (via gui.__init__), so we need a fresh load 
# or direct read to avoid circular dependency issues if they exist.
# load_config() is safe as it only uses standard libraries.
_config, _, _, _ = load_config()
_force_standard_tk = _config.get("ui_force_standard_tk", False)

HAVE_CTK = False
ctk = None
CTkImage = None

if not _force_standard_tk:
    try:
        import customtkinter as ctk
        from customtkinter import CTkImage as _CTkImage
        HAVE_CTK = True
        CTkImage = _CTkImage
    except ImportError:
        HAVE_CTK = False
        ctk = None
        CTkImage = None
else:
    # Forced fallback
    HAVE_CTK = False
    ctk = None
    CTkImage = None
