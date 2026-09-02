"""Tests for OpenAI / ElevenLabs provider payload builders via importlib."""

from __future__ import annotations

import importlib.util
import json
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


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


def test_openai_payload_has_required_fields(tts_clip_module) -> None:
    p = tts_clip_module.build_openai_payload("hello world", "alloy", "tts-1")
    assert p["model"] == "tts-1"
    assert p["voice"] == "alloy"
    assert p["input"] == "hello world"
    assert p["response_format"] == "mp3"


def test_openai_payload_omits_streaming_flag(tts_clip_module) -> None:
    """OpenAI Audio Speech doesn't stream — we just download and pipe."""
    p = tts_clip_module.build_openai_payload("hi", "nova", "tts-1-hd")
    assert "stream" not in p


def test_openai_payload_supports_hd_model(tts_clip_module) -> None:
    p = tts_clip_module.build_openai_payload("hi", "echo", "tts-1-hd")
    assert p["model"] == "tts-1-hd"


def test_openai_payload_supports_gpt4o_mini_tts(tts_clip_module) -> None:
    p = tts_clip_module.build_openai_payload("hi", "shimmer", "gpt-4o-mini-tts")
    assert p["model"] == "gpt-4o-mini-tts"


def test_openai_payload_is_json_serializable(tts_clip_module) -> None:
    """The payload must survive json.dumps with ensure_ascii=False (for unicode text)."""
    p = tts_clip_module.build_openai_payload("héllo 🌍", "alloy", "tts-1")
    encoded = json.dumps(p, ensure_ascii=False)
    decoded = json.loads(encoded)
    assert decoded["input"] == "héllo 🌍"


# ---------------------------------------------------------------------------
# ElevenLabs
# ---------------------------------------------------------------------------


def test_elevenlabs_payload_has_required_fields(tts_clip_module) -> None:
    voice_id = "21m00Tcm4TlvDq8ikWAM"
    p = tts_clip_module.build_elevenlabs_payload("hi", voice_id, "eleven_monolingual_v1")
    assert p["text"] == "hi"
    assert p["model_id"] == "eleven_monolingual_v1"
    assert "voice_settings" in p
    assert "stability" in p["voice_settings"]
    assert "similarity_boost" in p["voice_settings"]


def test_elevenlabs_voice_is_voice_id_not_name(tts_clip_module) -> None:
    """The CLI's ``--voice`` for ElevenLabs is a voice_id (e.g. ``21m00...``)."""
    p = tts_clip_module.build_elevenlabs_payload(
        "hi", "21m00Tcm4TlvDq8ikWAM", "eleven_monolingual_v1"
    )
    assert p.get("voice_id") is None  # not in the payload; it's part of the URL
    assert "voice" not in p  # not used in payload; lives in URL


def test_elevenlabs_payload_supports_multilingual_v2(tts_clip_module) -> None:
    p = tts_clip_module.build_elevenlabs_payload(
        "hi", "21m00Tcm4TlvDq8ikWAM", "eleven_multilingual_v2"
    )
    assert p["model_id"] == "eleven_multilingual_v2"


def test_elevenlabs_payload_is_json_serializable(tts_clip_module) -> None:
    p = tts_clip_module.build_elevenlabs_payload(
        "héllo 🌍", "21m00Tcm4TlvDq8ikWAM", "eleven_monolingual_v1"
    )
    encoded = json.dumps(p, ensure_ascii=False)
    decoded = json.loads(encoded)
    assert decoded["text"] == "héllo 🌍"


# ---------------------------------------------------------------------------
# MiniMax (sanity)
# ---------------------------------------------------------------------------


def test_mini_max_payload_uses_nested_voice_setting(tts_clip_module) -> None:
    p = tts_clip_module.build_mini_max_payload("hi", "English_Graceful_Lady", "speech-02-turbo")
    assert p["model"] == "speech-02-turbo"
    assert p["text"] == "hi"
    assert p["stream"] is True
    assert p["voice_setting"]["voice_id"] == "English_Graceful_Lady"
    assert p["audio_setting"]["format"] == "mp3"
    assert p["audio_setting"]["sample_rate"] == 32000
