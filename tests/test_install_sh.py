"""install.sh contract tests."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

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


def test_install_sh_does_not_embed_any_real_secrets() -> None:
    """The literal prefix ``sk-cp-`` is fine in prompt copy, but no real key."""
    content = INSTALL.read_text()
    real_key = re.search(r"sk-cp-[A-Za-z0-9_-]{30,}", content)
    assert not real_key, f"possible embedded key in install.sh: {real_key.group(0)[:20]}..."
    assert "paste your" in content.lower(), "install.sh should prompt for the key"


@pytest.mark.parametrize(
    "provider,env_key",
    [
        ("MiniMax", "MiniMax_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("elevenlabs", "ELEVENLABS_API_KEY"),
    ],
)
def test_install_sh_handles_each_provider(provider: str, env_key: str) -> None:
    content = INSTALL.read_text()
    assert provider in content, f"{provider} not mentioned in install.sh"
    assert env_key in content, f"{env_key} not referenced in install.sh"


def test_install_sh_lists_provider_choices_in_prompt() -> None:
    content = INSTALL.read_text()
    # The interactive prompt should mention all three providers.
    assert "1)" in content and "2)" in content and "3)" in content


def test_install_sh_writes_tts_provider_line() -> None:
    """The env file must record which provider was chosen."""
    content = INSTALL.read_text()
    assert "TTS_PROVIDER=" in content, "install.sh must write TTS_PROVIDER=... to env"
