"""Tests for tts_clip — runs against the live script without importing it."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tts_clip.py"


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


def test_script_runs_without_args_shows_help_or_runs() -> None:
    """Either shows help (bad args) or runs cleanly. No segfault / import error."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    # rc=0 (empty clipboard, no key configured → "not set" error rc=3) or rc=3 is fine.
    # What we forbid is rc=1 with a Python traceback.
    if result.returncode != 0:
        assert "Traceback" not in result.stderr, result.stderr
        assert "ImportError" not in result.stderr, result.stderr


def test_script_unknown_provider_exits_nonzero() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--provider", "bogus"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    # argparse should reject the bad choice (rc=2) before main() runs.
    assert result.returncode != 0
