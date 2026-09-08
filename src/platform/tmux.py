"""
Linux tmux session management and desktop terminal attachment.

Kept free of GUI, tray, config, provider, and main imports so it can be safely
used at early startup and in background threads.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from .detect import is_linux

TMUX_SESSION_NAME = "aipromptbridge"

# Terminal basename -> function(base_argv, attach_command) -> full_argv
TERMINAL_EXEC_BUILDERS: Dict[str, Callable[[List[str], List[str]], List[str]]] = {
    "foot": lambda base, command: [*base, "-e", *command],
    "kitty": lambda base, command: [*base, "-e", *command],
    "alacritty": lambda base, command: [*base, "-e", *command],
    "ghostty": lambda base, command: [*base, "-e", *command],
    "wezterm": lambda base, command: [*base, "start", "--", *command],
    "gnome-terminal": lambda base, command: [*base, "--", *command],
    "konsole": lambda base, command: [*base, "-e", *command],
    "xfce4-terminal": lambda base, command: [*base, "-x", *command],
    "xterm": lambda base, command: [*base, "-e", *command],
}

_FALLBACK_TERMINAL_CANDIDATES = (
    "foot",
    "kitty",
    "alacritty",
    "wezterm",
    "ghostty",
    "gnome-terminal",
    "konsole",
    "xfce4-terminal",
    "xterm",
)


def is_tmux_available() -> bool:
    """Return True if running on Linux and tmux is available on PATH."""
    return is_linux() and shutil.which("tmux") is not None


def is_inside_tmux() -> bool:
    """Return True if currently running inside a tmux session."""
    return bool(os.environ.get("TMUX"))


def build_tmux_new_session_command(app_command: list[str], *, detached: bool) -> list[str]:
    """
    Build argv for creating or attaching to the named tmux session.

    With -A, tmux attaches to an existing session with the given name if one exists;
    otherwise, it creates a new session running app_command.
    """
    command = ["tmux", "new-session"]
    if detached:
        command.append("-d")
    command.extend(["-A", "-s", TMUX_SESSION_NAME, *app_command])
    return command


def session_exists(session_name: str = TMUX_SESSION_NAME) -> bool:
    """Check whether a tmux session with the specified name exists."""
    if not is_tmux_available():
        return False
    try:
        res = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return res.returncode == 0
    except OSError:
        return False


def maybe_exec_in_tmux(app_command: list[str], *, detached: bool) -> bool:
    """
    Re-exec the current process inside tmux if on Linux and tmux is available.

    Returns False if skipped (not Linux, tmux unavailable, or already in tmux).
    If os.execvpe succeeds, this call does not return.
    """
    if not is_tmux_available() or is_inside_tmux():
        return False

    command = build_tmux_new_session_command(app_command, detached=detached)
    env = os.environ.copy()
    env["AIPROMPTBRIDGE_TMUX_LAUNCHED"] = "1"
    os.execvpe("tmux", command, env)
    return True


def _resolve_terminal_argv(attach_command: list[str]) -> Tuple[List[str], str]:
    """
    Resolve terminal emulator argv to attach to tmux.

    Returns:
        (terminal_argv, terminal_display_name)
    Raises:
        RuntimeError: if no suitable terminal emulator is found.
    """
    # 1. Prefer xdg-terminal-exec
    if shutil.which("xdg-terminal-exec"):
        return ["xdg-terminal-exec", *attach_command], "xdg-terminal-exec"

    # 2. Check $TERMINAL environment variable
    terminal_env = os.environ.get("TERMINAL", "").strip()
    if terminal_env:
        try:
            tokens = shlex.split(terminal_env)
        except ValueError:
            tokens = []
        if tokens:
            exe_name = Path(tokens[0]).name
            builder = TERMINAL_EXEC_BUILDERS.get(exe_name, lambda base, cmd: [*base, "-e", *cmd])
            return builder(tokens, attach_command), terminal_env

    # 3. Check installed common terminals in priority order
    for cand in _FALLBACK_TERMINAL_CANDIDATES:
        path = shutil.which(cand)
        if path:
            builder = TERMINAL_EXEC_BUILDERS.get(cand, lambda base, cmd: [*base, "-e", *cmd])
            return builder([path], attach_command), cand

    candidates_list = ", ".join(["xdg-terminal-exec", "$TERMINAL", *_FALLBACK_TERMINAL_CANDIDATES])
    raise RuntimeError(f"Could not find a supported terminal emulator (checked: {candidates_list}).")


def open_terminal_and_attach(session_name: str = TMUX_SESSION_NAME) -> Tuple[bool, str]:
    """
    Launch the desktop's default terminal and attach it to the named tmux session.

    Returns:
        (success: bool, message: str)
    """
    if not is_tmux_available():
        return False, "tmux is not installed or not available on PATH."

    if not session_exists(session_name):
        return False, f"No active tmux session '{session_name}' found."

    attach_command = ["tmux", "attach-session", "-t", session_name]

    try:
        terminal_argv, terminal_name = _resolve_terminal_argv(attach_command)
    except RuntimeError as exc:
        return False, str(exc)

    try:
        subprocess.Popen(
            terminal_argv,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True, f"Opened terminal ({terminal_name}) attached to tmux session '{session_name}'."
    except OSError as exc:
        return False, f"Failed to launch terminal ({terminal_name}): {exc}"
