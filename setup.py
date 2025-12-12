#!/usr/bin/env python3
"""
cx_Freeze setup script for AI Bridge
Creates a standalone Windows executable with console window (can be hidden/shown via tray)

Build commands:
    python setup.py build        # Build executable
    python setup.py bdist_msi    # Build MSI installer (Windows)

Output:
    build/exe.win-amd64-3.x/     # Executable folder
"""

import sys
from pathlib import Path
from cx_Freeze import setup, Executable

# ─── Build Options ────────────────────────────────────────────────────────────

# Dependencies are automatically detected, but we need to fine-tune
build_exe_options = {
    # Packages to include
    "packages": [
        "flask",
        "requests",
        "pynput",
        "pyperclip",
        "darkdetect",
        "tkinter",
        "json",
        "threading",
        "logging",
        "rich",
        "infi.systray",
    ],
    
    # Modules to exclude (reduce size)
    "excludes": [
        "unittest",
        "test",
        "tests",
        "numpy",
        "pandas",
        "scipy",
        "matplotlib",
        "PIL",
        "cv2",
        "email",
        "xml.dom",
        "xmlrpc",
        "curses",
    ],
    
    # Files to include
    "include_files": [
        ("icon.ico", "icon.ico"),
        ("text_edit_tool_options.json", "text_edit_tool_options.json"),
        # Note: config.ini is generated on first run if not exists
    ],
    
    # Optimize bytecode
    "optimize": 2,
    
    # Include all source files in a zip (cleaner output)
    "zip_include_packages": ["*"],
    "zip_exclude_packages": [],
}

# ─── Executable Configuration ─────────────────────────────────────────────────

# Use "console" base to keep the console window (can be hidden/shown via tray)
# This is different from "gui" which has no console at all
base = "console"

executables = [
    Executable(
        script="main.py",
        base=base,
        target_name="AIBridge.exe",
        icon="icon.ico",
        copyright="AI Bridge",
        # Windows-specific options
        shortcut_name="AI Bridge",
        shortcut_dir="DesktopFolder",
    )
]

# ─── Setup ────────────────────────────────────────────────────────────────────

setup(
    name="AI Bridge",
    version="1.0.0",
    description="Multi-modal AI Assistant Server with TextEditTool",
    author="AI Bridge",
    options={"build_exe": build_exe_options},
    executables=executables,
)