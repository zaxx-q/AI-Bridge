"""Unit tests for Linux tmux session management and terminal attachment."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.platform import tmux


class TestTmuxAvailability:
    def test_is_tmux_available_linux_and_which(self):
        with (
            patch("src.platform.tmux.is_linux", return_value=True),
            patch("shutil.which", return_value="/usr/bin/tmux"),
        ):
            assert tmux.is_tmux_available() is True

        with patch("src.platform.tmux.is_linux", return_value=True), patch("shutil.which", return_value=None):
            assert tmux.is_tmux_available() is False

        with (
            patch("src.platform.tmux.is_linux", return_value=False),
            patch("shutil.which", return_value="/usr/bin/tmux"),
        ):
            assert tmux.is_tmux_available() is False

    def test_is_inside_tmux(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1234,0")
        assert tmux.is_inside_tmux() is True

        monkeypatch.delenv("TMUX", raising=False)
        assert tmux.is_inside_tmux() is False


class TestTmuxCommandBuilders:
    def test_build_tmux_new_session_command_interactive(self):
        cmd = tmux.build_tmux_new_session_command(["python3", "main.py", "--show-console"], detached=False)
        assert cmd == ["tmux", "new-session", "-A", "-s", "aipromptbridge", "python3", "main.py", "--show-console"]

    def test_build_tmux_new_session_command_detached(self):
        cmd = tmux.build_tmux_new_session_command(["python3", "main.py", "--tmux-detached"], detached=True)
        assert cmd == [
            "tmux",
            "new-session",
            "-d",
            "-A",
            "-s",
            "aipromptbridge",
            "python3",
            "main.py",
            "--tmux-detached",
        ]


class TestSessionExists:
    def test_session_exists_false_when_tmux_unavailable(self):
        with patch("src.platform.tmux.is_tmux_available", return_value=False):
            assert tmux.session_exists("aipromptbridge") is False

    def test_session_exists_subprocess_success_and_failure(self):
        with (
            patch("src.platform.tmux.is_tmux_available", return_value=True),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            assert tmux.session_exists("aipromptbridge") is True
            mock_run.assert_called_with(
                ["tmux", "has-session", "-t", "aipromptbridge"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

            mock_run.return_value = MagicMock(returncode=1)
            assert tmux.session_exists("aipromptbridge") is False

    def test_session_exists_handles_oserror(self):
        with (
            patch("src.platform.tmux.is_tmux_available", return_value=True),
            patch("subprocess.run", side_effect=OSError("tmux failed")),
        ):
            assert tmux.session_exists("aipromptbridge") is False


class TestMaybeExecInTmux:
    def test_maybe_exec_skips_if_not_linux(self):
        with (
            patch("src.platform.tmux.is_tmux_available", return_value=False),
            patch("os.execvpe") as mock_exec,
        ):
            assert tmux.maybe_exec_in_tmux(["python3", "main.py"], detached=False) is False
            mock_exec.assert_not_called()

    def test_maybe_exec_skips_if_inside_tmux(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1,0")
        with (
            patch("src.platform.tmux.is_tmux_available", return_value=True),
            patch("os.execvpe") as mock_exec,
        ):
            assert tmux.maybe_exec_in_tmux(["python3", "main.py"], detached=False) is False
            mock_exec.assert_not_called()

    def test_maybe_exec_calls_execvpe(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TMUX", raising=False)
        monkeypatch.setenv("TEST_VAR", "123")

        with (
            patch("src.platform.tmux.is_tmux_available", return_value=True),
            patch("os.execvpe") as mock_exec,
        ):
            tmux.maybe_exec_in_tmux(["python3", "main.py"], detached=False)
            mock_exec.assert_called_once()
            file_arg, argv_arg, env_arg = mock_exec.call_args[0]
            assert file_arg == "tmux"
            assert argv_arg == ["tmux", "new-session", "-A", "-s", "aipromptbridge", "python3", "main.py"]
            assert env_arg.get("AIPROMPTBRIDGE_TMUX_LAUNCHED") == "1"
            assert env_arg.get("TEST_VAR") == "123"


class TestOpenTerminalAndAttach:
    def test_rejects_when_tmux_unavailable(self):
        with (
            patch("src.platform.tmux.is_tmux_available", return_value=False),
            patch("subprocess.Popen") as mock_popen,
        ):
            ok, msg = tmux.open_terminal_and_attach("aipromptbridge")
            assert ok is False
            assert "tmux is not installed" in msg
            mock_popen.assert_not_called()

    def test_rejects_when_session_not_found(self):
        with (
            patch("src.platform.tmux.is_tmux_available", return_value=True),
            patch("src.platform.tmux.session_exists", return_value=False),
            patch("subprocess.Popen") as mock_popen,
        ):
            ok, msg = tmux.open_terminal_and_attach("aipromptbridge")
            assert ok is False
            assert "No active tmux session" in msg
            mock_popen.assert_not_called()

    def test_uses_xdg_terminal_exec_first(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TERMINAL", raising=False)

        def mock_which(cmd):
            if cmd == "xdg-terminal-exec":
                return "/usr/bin/xdg-terminal-exec"
            return None

        with (
            patch("src.platform.tmux.is_tmux_available", return_value=True),
            patch("src.platform.tmux.session_exists", return_value=True),
            patch("shutil.which", side_effect=mock_which),
            patch("subprocess.Popen") as mock_popen,
        ):
            ok, msg = tmux.open_terminal_and_attach("aipromptbridge")
            assert ok is True
            assert "xdg-terminal-exec" in msg
            mock_popen.assert_called_once_with(
                ["xdg-terminal-exec", "tmux", "attach-session", "-t", "aipromptbridge"],
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

    def test_uses_terminal_env_var(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TERMINAL", "wezterm")

        def mock_which(cmd):
            if cmd == "xdg-terminal-exec":
                return None
            return f"/usr/bin/{cmd}"

        with (
            patch("src.platform.tmux.is_tmux_available", return_value=True),
            patch("src.platform.tmux.session_exists", return_value=True),
            patch("shutil.which", side_effect=mock_which),
            patch("subprocess.Popen") as mock_popen,
        ):
            ok, msg = tmux.open_terminal_and_attach("aipromptbridge")
            assert ok is True
            assert "wezterm" in msg
            mock_popen.assert_called_once_with(
                ["wezterm", "start", "--", "tmux", "attach-session", "-t", "aipromptbridge"],
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

    def test_uses_terminal_env_var_custom_with_args(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TERMINAL", "custom-term --title MyTerm")

        def mock_which(cmd):
            return None

        with (
            patch("src.platform.tmux.is_tmux_available", return_value=True),
            patch("src.platform.tmux.session_exists", return_value=True),
            patch("shutil.which", side_effect=mock_which),
            patch("subprocess.Popen") as mock_popen,
        ):
            ok, msg = tmux.open_terminal_and_attach("aipromptbridge")
            assert ok is True
            assert "custom-term" in msg
            mock_popen.assert_called_once_with(
                ["custom-term", "--title", "MyTerm", "-e", "tmux", "attach-session", "-t", "aipromptbridge"],
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

    @pytest.mark.parametrize(
        "candidate,expected_args",
        [
            ("foot", ["/usr/bin/foot", "-e", "tmux", "attach-session", "-t", "aipromptbridge"]),
            ("kitty", ["/usr/bin/kitty", "-e", "tmux", "attach-session", "-t", "aipromptbridge"]),
            ("alacritty", ["/usr/bin/alacritty", "-e", "tmux", "attach-session", "-t", "aipromptbridge"]),
            ("ghostty", ["/usr/bin/ghostty", "-e", "tmux", "attach-session", "-t", "aipromptbridge"]),
            ("wezterm", ["/usr/bin/wezterm", "start", "--", "tmux", "attach-session", "-t", "aipromptbridge"]),
            ("gnome-terminal", ["/usr/bin/gnome-terminal", "--", "tmux", "attach-session", "-t", "aipromptbridge"]),
            ("konsole", ["/usr/bin/konsole", "-e", "tmux", "attach-session", "-t", "aipromptbridge"]),
            ("xfce4-terminal", ["/usr/bin/xfce4-terminal", "-x", "tmux", "attach-session", "-t", "aipromptbridge"]),
            ("xterm", ["/usr/bin/xterm", "-e", "tmux", "attach-session", "-t", "aipromptbridge"]),
        ],
    )
    def test_candidate_terminals_argv(self, candidate, expected_args, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TERMINAL", raising=False)

        def mock_which(cmd):
            if cmd == candidate:
                return f"/usr/bin/{candidate}"
            return None

        with (
            patch("src.platform.tmux.is_tmux_available", return_value=True),
            patch("src.platform.tmux.session_exists", return_value=True),
            patch("shutil.which", side_effect=mock_which),
            patch("subprocess.Popen") as mock_popen,
        ):
            ok, msg = tmux.open_terminal_and_attach("aipromptbridge")
            assert ok is True
            assert candidate in msg
            mock_popen.assert_called_once_with(
                expected_args,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

    def test_no_terminal_found(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TERMINAL", raising=False)

        with (
            patch("src.platform.tmux.is_tmux_available", return_value=True),
            patch("src.platform.tmux.session_exists", return_value=True),
            patch("shutil.which", return_value=None),
            patch("subprocess.Popen") as mock_popen,
        ):
            ok, msg = tmux.open_terminal_and_attach("aipromptbridge")
            assert ok is False
            assert "Could not find a supported terminal" in msg
            mock_popen.assert_not_called()

    def test_popen_oserror_handled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TERMINAL", raising=False)

        with (
            patch("src.platform.tmux.is_tmux_available", return_value=True),
            patch("src.platform.tmux.session_exists", return_value=True),
            patch("shutil.which", side_effect=lambda cmd: "/usr/bin/foot" if cmd == "foot" else None),
            patch("subprocess.Popen", side_effect=OSError("Exec format error")),
        ):
            ok, msg = tmux.open_terminal_and_attach("aipromptbridge")
            assert ok is False
            assert "Failed to launch terminal" in msg
