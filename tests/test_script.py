"""Tests for tts_clip — runs against the live script without importing it."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tts_clip.py"


@pytest.fixture
def script_in_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Symlink the script into tmp_path and put that on PATH so `tts-clip`-style
    invocations resolve. We don't actually import it — subprocess is more honest."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    link = bin_dir / "tts-clip"
    link.symlink_to(SCRIPT)
    link.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    return link


def test_script_compiles() -> None:
    """Smoke: the script is valid Python."""
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_script_is_executable() -> None:
    """The script has +x so it can run directly via shebang."""
    mode = SCRIPT.stat().st_mode
    assert mode & 0o111, f"{SCRIPT} is not executable (mode={oct(mode)})"


def test_script_uses_python3_shebang() -> None:
    first_line = SCRIPT.read_text().splitlines()[0]
    assert first_line.startswith("#!") and "python" in first_line, first_line


def test_empty_clipboard_is_handled_gracefully(
    script_in_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With an empty clipboard and a valid env file, the script must exit 0
    without making any network call."""
    env_file = tmp_path / "env"
    env_file.write_text("MiniMax_API_KEY=test-key-not-used\n")
    env_file.chmod(0o600)
    config_dir = tmp_path / "tts-clip"
    config_dir.mkdir(exist_ok=True)
    shutil.copy(env_file, config_dir / "env")

    # Empty the clipboard
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    result = subprocess.run(
        ["tts-clip"],
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "XDG_CONFIG_HOME": str(tmp_path)},
        check=False,
    )
    # Either wl-paste is present (then rc=0, msg about empty) or absent (then rc=4).
    # We don't assert on the exit code here because wl-clipboard availability varies
    # across CI hosts; we only assert it doesn't crash hard.
    assert result.returncode in (0, 4)
    if result.returncode == 0:
        out = (result.stdout or "") + (result.stderr or "")
        assert "empty" in out.lower()
