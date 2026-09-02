"""Pure-function tests for parse_sse_event via importlib."""

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


def _sse(audio: str | None = None, status: int | None = 1, base_code: int | None = 0) -> str:
    payload: dict[str, object] = {}
    if base_code is not None:
        payload["base_resp"] = {"status_code": base_code, "status_msg": "ok"}
    data: dict[str, object] = {"status": status}
    if audio is not None:
        data["audio"] = audio
    payload["data"] = data
    return "data: " + json.dumps(payload)


def test_non_data_line_is_skipped(tts_clip_module) -> None:
    ev = tts_clip_module.parse_sse_event("event: ping")
    assert ev.kind == "skip"
    assert ev.audio == b""


def test_empty_line_is_skipped(tts_clip_module) -> None:
    assert tts_clip_module.parse_sse_event("").kind == "skip"
    assert tts_clip_module.parse_sse_event("   ").kind == "skip"


def test_invalid_json_is_skipped(tts_clip_module) -> None:
    assert tts_clip_module.parse_sse_event("data: {not json").kind == "skip"


def test_progress_delta_is_skipped(tts_clip_module) -> None:
    # status=1 with audio = streaming delta → must be skipped to avoid the
    # "repeats twice" bug from chunk 0..5 vs. the cumulative chunk 6.
    assert tts_clip_module.parse_sse_event(_sse(audio="ff", status=1)).kind == "skip"


def test_final_chunk_returns_decoded_audio(tts_clip_module) -> None:
    # status=2 with audio = the complete audio, decode it
    hex_audio = "49443304"  # "ID3\x04"
    ev = tts_clip_module.parse_sse_event(_sse(audio=hex_audio, status=2))
    assert ev.kind == "final"
    assert ev.audio == bytes.fromhex(hex_audio)


def test_final_chunk_with_empty_audio_still_finishes(tts_clip_module) -> None:
    # Defensive: status=2 with empty audio shouldn't crash
    ev = tts_clip_module.parse_sse_event(_sse(audio="", status=2))
    assert ev.kind == "final"
    assert ev.audio == b""


def test_base_resp_error_short_circuits(tts_clip_module) -> None:
    ev = tts_clip_module.parse_sse_event(
        _sse(audio="ff", status=1, base_code=2013),
    )
    assert ev.kind == "error"
    assert ev.code == 2013
    assert ev.message == "ok"


def test_base_resp_success_status_is_ignored(tts_clip_module) -> None:
    # status_code == 0 is the success sentinel — should not be treated as an error
    ev = tts_clip_module.parse_sse_event(_sse(audio="ff", status=1, base_code=0))
    assert ev.kind == "skip"


def test_hex_decoding_handles_uppercase(tts_clip_module) -> None:
    hex_audio = "DEADBEEF"
    ev = tts_clip_module.parse_sse_event(_sse(audio=hex_audio, status=2))
    assert ev.audio == b"\xde\xad\xbe\xef"


def test_large_audio_chunk_decodes_correctly(tts_clip_module) -> None:
    # 1 KB of audio
    hex_audio = "00" * 1024
    ev = tts_clip_module.parse_sse_event(_sse(audio=hex_audio, status=2))
    assert len(ev.audio) == 1024
    assert ev.audio == b"\x00" * 1024
