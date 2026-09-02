"""install.sh contract tests."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL = REPO_ROOT / "install.sh"


def test_install_sh_exists() -> None:
    assert INSTALL.is_file()


def test_install_sh_is_executable() -> None:
    mode = INSTALL.stat().st_mode
    assert mode & 0o111


def test_install_sh_has_no_syntax_errors() -> None:
    result = subprocess.run(
        ["bash", "-n", str(INSTALL)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_install_sh_references_current_script_name() -> None:
    """install.sh must look for the renamed tts_clip.py (not tts-clip.py)."""
    content = INSTALL.read_text()
    assert "tts_clip.py" in content
    assert "tts-clip.py" not in content, "stale tts-clip.py reference in install.sh"


def test_install_sh_creates_env_file_mode_600() -> None:
    """The script must chmod 600 the env file."""
    content = INSTALL.read_text()
    assert re.search(r"chmod\s+600", content), "install.sh must chmod 600 the env file"


def test_install_sh_does_not_embed_any_secrets() -> None:
    """The install script must not hard-code a real API key.

    The literal prefix ``sk-cp-`` is fine to mention (e.g. in prompt copy) but
    anything that looks like a full key (40+ chars after the prefix) is not.
    """
    content = INSTALL.read_text()
    # Look for sk-cp- followed by >= 40 hex-ish chars, NOT a placeholder
    real_key = re.search(r"sk-cp-[A-Za-z0-9_-]{30,}", content)
    assert not real_key, f"possible embedded key in install.sh: {real_key.group(0)[:20]}..."
    assert (
        "your MiniMax" in content or "paste your" in content.lower()
    ), "install.sh should prompt the user for their key"
