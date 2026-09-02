"""Tests for load_api_key via importlib."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tts_clip.py"


@pytest.fixture(scope="module")
def tts_clip_module():
    spec = importlib.util.spec_from_file_location("tts_clip", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load tts_clip.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["tts_clip"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def isolated_env_file(tts_clip_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    env_file = tmp_path / "tts-clip" / "env"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tts_clip_module, "ENV_FILE", env_file)
    return env_file


def test_loads_simple_key(isolated_env_file: Path, tts_clip_module) -> None:
    isolated_env_file.write_text("MiniMax_API_KEY=sk-test-123\n")
    assert tts_clip_module.load_api_key() == "sk-test-123"


def test_loads_key_with_double_quotes(isolated_env_file: Path, tts_clip_module) -> None:
    isolated_env_file.write_text('MiniMax_API_KEY="sk-test-456"\n')
    assert tts_clip_module.load_api_key() == "sk-test-456"


def test_loads_key_with_single_quotes(isolated_env_file: Path, tts_clip_module) -> None:
    isolated_env_file.write_text("MiniMax_API_KEY='sk-test-789'\n")
    assert tts_clip_module.load_api_key() == "sk-test-789"


def test_skips_comment_lines(isolated_env_file: Path, tts_clip_module) -> None:
    isolated_env_file.write_text("# this is a comment\nMiniMax_API_KEY=sk-real\n# another\n")
    assert tts_clip_module.load_api_key() == "sk-real"


def test_skips_blank_lines(isolated_env_file: Path, tts_clip_module) -> None:
    isolated_env_file.write_text("\n\nMiniMax_API_KEY=sk-real\n\n")
    assert tts_clip_module.load_api_key() == "sk-real"


def test_missing_key_exits(isolated_env_file: Path, tts_clip_module) -> None:
    isolated_env_file.write_text("OTHER_VAR=foo\n")
    with pytest.raises(SystemExit) as exc:
        tts_clip_module.load_api_key()
    assert exc.value.code == 3


def test_missing_file_exits(
    tts_clip_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "does-not-exist" / "env"
    monkeypatch.setattr(tts_clip_module, "ENV_FILE", missing)
    with pytest.raises(SystemExit) as exc:
        tts_clip_module.load_api_key()
    assert exc.value.code == 4


def test_placeholder_value_exits(isolated_env_file: Path, tts_clip_module) -> None:
    isolated_env_file.write_text("MiniMax_API_KEY=PASTE-NEW-KEY-HERE\n")
    with pytest.raises(SystemExit) as exc:
        tts_clip_module.load_api_key()
    assert exc.value.code == 3


def test_empty_value_exits(isolated_env_file: Path, tts_clip_module) -> None:
    isolated_env_file.write_text("MiniMax_API_KEY=\n")
    with pytest.raises(SystemExit) as exc:
        tts_clip_module.load_api_key()
    assert exc.value.code == 3


def test_whitespace_around_key_is_trimmed(isolated_env_file: Path, tts_clip_module) -> None:
    isolated_env_file.write_text("  MiniMax_API_KEY  =  sk-trimmed  \n")
    assert tts_clip_module.load_api_key() == "sk-trimmed"


def test_xdg_config_home_is_honored(
    tts_clip_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When XDG_CONFIG_HOME is set, the script reads from there, not ~/.config."""
    custom = tmp_path / "custom-cfg"
    (custom / "tts-clip").mkdir(parents=True)
    (custom / "tts-clip" / "env").write_text("MiniMax_API_KEY=sk-xdg\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(custom))
    cfg = tts_clip_module.Path(os.environ["XDG_CONFIG_HOME"]) / "tts-clip"
    monkeypatch.setattr(tts_clip_module, "CONFIG_DIR", cfg)
    monkeypatch.setattr(tts_clip_module, "ENV_FILE", cfg / "env")
    assert tts_clip_module.load_api_key() == "sk-xdg"


def test_lax_permissions_still_loads(isolated_env_file: Path, tts_clip_module) -> None:
    """Best practice: env file should be 0600. We don't fail on lax perms."""
    isolated_env_file.write_text("MiniMax_API_KEY=sk-anything\n")
    isolated_env_file.chmod(0o644)  # intentionally lax
    assert tts_clip_module.load_api_key() == "sk-anything"
