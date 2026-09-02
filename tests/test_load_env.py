"""Tests for load_env via importlib."""

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


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


def test_missing_file_returns_empty_dict(tts_clip_module, tmp_path: Path) -> None:
    """No env file → empty dict, not an exception."""
    out = tts_clip_module.load_env(tmp_path / "env")
    assert out == {}


def test_simple_key_value(tts_clip_module, tmp_path: Path) -> None:
    p = tmp_path / "env"
    _write(p, "OPENAI_API_KEY=sk-test-123\n")
    assert tts_clip_module.load_env(p) == {"OPENAI_API_KEY": "sk-test-123"}


def test_double_quoted_value_is_stripped(tts_clip_module, tmp_path: Path) -> None:
    p = tmp_path / "env"
    _write(p, 'OPENAI_API_KEY="sk-test-456"\n')
    assert tts_clip_module.load_env(p)["OPENAI_API_KEY"] == "sk-test-456"


def test_single_quoted_value_is_stripped(tts_clip_module, tmp_path: Path) -> None:
    p = tmp_path / "env"
    _write(p, "OPENAI_API_KEY='sk-test-789'\n")
    assert tts_clip_module.load_env(p)["OPENAI_API_KEY"] == "sk-test-789"


def test_comments_and_blanks_are_ignored(tts_clip_module, tmp_path: Path) -> None:
    p = tmp_path / "env"
    _write(
        p,
        "# header comment\n\nTTS_PROVIDER=MiniMax\n# another comment\nMiniMax_API_KEY=sk-real\n\n",
    )
    out = tts_clip_module.load_env(p)
    assert out == {"TTS_PROVIDER": "MiniMax", "MiniMax_API_KEY": "sk-real"}


def test_multiple_provider_keys_can_coexist(tts_clip_module, tmp_path: Path) -> None:
    """Switching providers should not require deleting the unused keys."""
    p = tmp_path / "env"
    _write(
        p,
        "TTS_PROVIDER=openai\n"
        "MiniMax_API_KEY=sk-cp-old\n"
        "OPENAI_API_KEY=sk-oai-123\n"
        "ELEVENLABS_API_KEY=el-123\n",
    )
    out = tts_clip_module.load_env(p)
    assert out["TTS_PROVIDER"] == "openai"
    assert out["MiniMax_API_KEY"] == "sk-cp-old"
    assert out["OPENAI_API_KEY"] == "sk-oai-123"
    assert out["ELEVENLABS_API_KEY"] == "el-123"


def test_whitespace_around_key_is_trimmed(tts_clip_module, tmp_path: Path) -> None:
    p = tmp_path / "env"
    _write(p, "  OPENAI_API_KEY  =  sk-trimmed  \n")
    assert tts_clip_module.load_env(p)["OPENAI_API_KEY"] == "sk-trimmed"


def test_value_containing_equals_sign_is_kept(tts_clip_module, tmp_path: Path) -> None:
    """``partition('=')`` splits only on the first '=' — base64 keys with '=' survive."""
    p = tmp_path / "env"
    _write(p, "OPENAI_API_KEY=sk-abc=def=ghi\n")
    assert tts_clip_module.load_env(p)["OPENAI_API_KEY"] == "sk-abc=def=ghi"


def test_empty_value_round_trips(tts_clip_module, tmp_path: Path) -> None:
    p = tmp_path / "env"
    _write(p, "OPENAI_API_KEY=\n")
    assert tts_clip_module.load_env(p)["OPENAI_API_KEY"] == ""


def test_placeholder_value_round_trips(tts_clip_module, tmp_path: Path) -> None:
    """The placeholder must survive parsing so main() can detect it."""
    p = tmp_path / "env"
    _write(p, "OPENAI_API_KEY=PASTE-NEW-KEY-HERE\n")
    assert tts_clip_module.load_env(p)["OPENAI_API_KEY"] == "PASTE-NEW-KEY-HERE"


def test_malformed_line_without_equals_is_skipped(tts_clip_module, tmp_path: Path) -> None:
    p = tmp_path / "env"
    _write(p, "OPENAI_API_KEY=sk-ok\nthis is not a key=value line\n")
    out = tts_clip_module.load_env(p)
    assert "OPENAI_API_KEY" in out
    assert len(out) == 1


def test_xdg_config_home_is_honored(
    tts_clip_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When XDG_CONFIG_HOME is set, the script reads from there, not ~/.config."""
    custom = tmp_path / "custom-cfg"
    (custom / "tts-clip").mkdir(parents=True)
    (custom / "tts-clip" / "env").write_text("MiniMax_API_KEY=sk-xdg\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(custom))
    cfg = tts_clip_module.Path(os.environ["XDG_CONFIG_HOME"]) / "tts-clip"
    p = cfg / "env"
    assert tts_clip_module.load_env(p)["MiniMax_API_KEY"] == "sk-xdg"
