"""Tests for the provider registry and CLI dispatch."""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
from contextlib import redirect_stdout
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


def test_all_providers_are_registered(tts_clip_module) -> None:
    assert set(tts_clip_module.PROVIDERS.keys()) == {"MiniMax", "openai", "elevenlabs"}


def test_each_provider_has_unique_env_key(tts_clip_module) -> None:
    keys = [info.env_key for info in tts_clip_module.PROVIDERS.values()]
    assert len(keys) == len(set(keys)), f"duplicate env keys: {keys}"


def test_each_provider_has_a_key_url(tts_clip_module) -> None:
    for info in tts_clip_module.PROVIDERS.values():
        assert info.key_url.startswith("http"), f"{info.name}: bad key_url={info.key_url!r}"


def test_default_provider_is_in_registry(tts_clip_module) -> None:
    assert tts_clip_module.DEFAULT_PROVIDER in tts_clip_module.PROVIDERS


def test_list_providers_runs_clean(tts_clip_module) -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        tts_clip_module.list_providers()
    out = buf.getvalue()
    for name in tts_clip_module.PROVIDERS:
        assert name in out, f"{name} missing from --list-providers output"
    assert "Claude" in out or "Anthropic" in out, "Claude caveat missing from output"


def test_list_providers_invokable_via_subprocess(tts_clip_module) -> None:
    """Smoke: run ``python tts_clip.py --list-providers`` as a separate process."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--list-providers"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "MiniMax" in result.stdout
    assert "openai" in result.stdout
    assert "elevenlabs" in result.stdout
    assert "Claude" in result.stdout or "Anthropic" in result.stdout


def test_help_lists_all_providers_in_choices() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0
    assert "MiniMax" in result.stdout
    assert "openai" in result.stdout
    assert "elevenlabs" in result.stdout


def test_resolve_provider_returns_none_for_unknown(tts_clip_module) -> None:
    import argparse

    args = argparse.Namespace(provider="nonexistent", voice=None, model=None)
    out = tts_clip_module._resolve_provider(args, {})
    assert out is None


def test_resolve_provider_returns_none_for_missing_key(tts_clip_module) -> None:
    import argparse

    args = argparse.Namespace(provider="openai", voice=None, model=None)
    env = {"TTS_PROVIDER": "openai"}  # OPENAI_API_KEY missing
    out = tts_clip_module._resolve_provider(args, env)
    assert out is None


def test_resolve_provider_returns_info_when_key_set(tts_clip_module) -> None:
    import argparse

    args = argparse.Namespace(provider="openai", voice=None, model=None)
    env = {"TTS_PROVIDER": "openai", "OPENAI_API_KEY": "sk-test"}
    info = tts_clip_module._resolve_provider(args, env)
    assert info is not None
    assert info.name == "openai"


def test_resolve_provider_rejects_placeholder_key(tts_clip_module) -> None:
    """Even if env has the key var, PASTE-NEW-KEY-HERE should fail."""
    import argparse

    args = argparse.Namespace(provider="openai", voice=None, model=None)
    env = {"TTS_PROVIDER": "openai", "OPENAI_API_KEY": "PASTE-NEW-KEY-HERE"}
    out = tts_clip_module._resolve_provider(args, env)
    assert out is None


def test_resolve_voice_model_prefers_cli_flags(tts_clip_module) -> None:
    import argparse

    args = argparse.Namespace(provider="openai", voice="nova", model="tts-1-hd")
    info = tts_clip_module.PROVIDERS["openai"]
    voice, model = tts_clip_module._resolve_voice_model(args, {}, info)
    assert voice == "nova"
    assert model == "tts-1-hd"


def test_resolve_voice_model_falls_back_to_env(tts_clip_module) -> None:
    import argparse

    args = argparse.Namespace(provider="openai", voice=None, model=None)
    env = {"OPENAI_VOICE": "shimmer", "OPENAI_MODEL": "gpt-4o-mini-tts"}
    info = tts_clip_module.PROVIDERS["openai"]
    voice, model = tts_clip_module._resolve_voice_model(args, env, info)
    assert voice == "shimmer"
    assert model == "gpt-4o-mini-tts"


def test_resolve_voice_model_falls_back_to_defaults(tts_clip_module) -> None:
    import argparse

    args = argparse.Namespace(provider="openai", voice=None, model=None)
    info = tts_clip_module.PROVIDERS["openai"]
    voice, model = tts_clip_module._resolve_voice_model(args, {}, info)
    assert voice == info.default_voice
    assert model == info.default_model
