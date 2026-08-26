"""Tests for YtDlpManager.update_if_needed(). Live investigation found
this always silently failed: "Failed to update yt-dlp: [Errno 2] No
such file or directory: 'pipx'" on every single download, forever. Two
bugs: (1) the guard `"/root/.local/bin/yt-dlp" in self.executable_paths`
tests whether a hardcoded string literal is in a hardcoded list
containing that same literal -- always True regardless of which
executable was actually found -- so the pipx branch always ran even
though this deployment installs yt-dlp via pip (requirements.txt:
yt-dlp>=2024.12.0), never pipx; (2) since pipx isn't installed, that
subprocess.run() call raised FileNotFoundError, which escaped to the
outer except before ever reaching the intended fallback, so yt-dlp
could never actually update at runtime.
"""

from unittest.mock import MagicMock, patch

# See test_anti_detection_escalation.py's comment for why this import
# guard is needed -- the module instantiates a yt-dlp-dependent
# singleton at import time that this test venv can't satisfy.
with patch("os.path.exists", return_value=True):
    from src.services.unified_download_service import YtDlpManager


class TestYtDlpManagerUpdate:
    def _manager_with_forced_recheck(self, executable_path: str) -> YtDlpManager:
        with patch("os.path.exists", return_value=True):
            manager = YtDlpManager()
        manager.current_executable = executable_path
        manager.last_version_check = None  # force needs_update() True
        return manager

    def test_pip_installed_yt_dlp_updates_via_pip_not_pipx(self):
        """The actual, common case in this deployment: yt-dlp found at
        a pip-installed console-script path (e.g. /usr/local/bin/yt-dlp
        or venv site-packages), not a pipx path."""
        manager = self._manager_with_forced_recheck("/usr/local/bin/yt-dlp")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = manager.update_if_needed()

        assert result is True
        called_command = mock_run.call_args_list[0].args[0]
        assert "pipx" not in called_command
        assert "pip" in called_command or "-m" in called_command

    def test_pipx_installed_yt_dlp_still_updates_via_pipx(self):
        """When yt-dlp genuinely was found at the pipx-managed path,
        pipx upgrade is still the right mechanism -- this case must
        keep working, not just the pip case."""
        manager = self._manager_with_forced_recheck("/root/.local/bin/yt-dlp")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = manager.update_if_needed()

        assert result is True
        called_command = mock_run.call_args_list[0].args[0]
        assert "pipx" in called_command

    def test_missing_update_tool_does_not_raise(self):
        """If the update mechanism's own executable is missing (the
        original bug's trigger), update_if_needed() must return False
        gracefully -- never let the exception escape and crash the
        download attempt that called it."""
        manager = self._manager_with_forced_recheck("/usr/local/bin/yt-dlp")

        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = manager.update_if_needed()

        assert result is False
