#!/usr/bin/env python3
"""tts-clip — speak the current Wayland clipboard via MiniMax TTS.

Reads MiniMax_API_KEY from ~/.config/tts-clip/env, sends the clipboard
text to the MiniMax T2A v2 streaming endpoint, parses the SSE response
(hex-encoded MP3 chunks), and pipes the decoded audio into mpv for
immediate playback. No file is written to disk.

Exit codes:
  0  ok (or empty clipboard, by design)
  1  unexpected error
  3  API or auth error (incl. final status_code != 0)
  4  environment / dependency missing (wl-paste, mpv, curl, key file)
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

API_URL = "https://api.minimax.io/v1/t2a_v2"
MODEL = "speech-02-turbo"
VOICE = "English_Graceful_Lady"
SAMPLE_RATE = 32000
BITRATE = 128000
MAX_CHARS = 50000
CURL_TIMEOUT_SEC = 300

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "tts-clip"
ENV_FILE = CONFIG_DIR / "env"


def load_api_key() -> str:
    if not ENV_FILE.is_file():
        print(f"error: env file not found at {ENV_FILE}", file=sys.stderr)
        sys.exit(4)
    for raw in ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        if key.strip() == "MiniMax_API_KEY":
            value = val.strip().strip('"').strip("'")
            if value and "PASTE-NEW-KEY-HERE" not in value:
                return value
            print(
                f"error: MiniMax_API_KEY in {ENV_FILE} is empty or still a placeholder; "
                "edit it to your real key",
                file=sys.stderr,
            )
            sys.exit(3)
    print(f"error: MiniMax_API_KEY not found in {ENV_FILE}", file=sys.stderr)
    sys.exit(3)


def need_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        print(f"error: required tool '{name}' not found in PATH", file=sys.stderr)
        sys.exit(4)
    return path


def read_clipboard() -> str:
    need_tool("wl-paste")
    try:
        result = subprocess.run(
            ["wl-paste", "--no-newline"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("error: timed out reading clipboard", file=sys.stderr)
        sys.exit(4)

    if result.returncode != 0 and not result.stdout:
        return ""
    if result.returncode != 0:
        print(
            f"error: wl-paste failed: {result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(4)
    return result.stdout


def stream_sse_to_mpv(
    payload: dict[str, object],
    api_key: str,
    mpv_proc: subprocess.Popen[bytes],
) -> int:
    """Stream SSE response from MiniMax into mpv's stdin.

    Returns 0 on success, 3 on API/auth error, 1 on other failure.
    """
    curl_bin = need_tool("curl")
    payload_str = json.dumps(payload, ensure_ascii=False)

    curl_proc = subprocess.Popen(
        [
            curl_bin,
            "-sS",
            "--no-buffer",
            "-N",
            "--max-time",
            str(CURL_TIMEOUT_SEC),
            "-X",
            "POST",
            API_URL,
            "-H",
            f"Authorization: Bearer {api_key}",
            "-H",
            "Content-Type: application/json",
            "-d",
            payload_str,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if curl_proc.stdout is None or mpv_proc.stdin is None:
        print("error: failed to open pipes to curl/mpv", file=sys.stderr)
        return 1

    curl_stdout = curl_proc.stdout
    mpv_stdin = mpv_proc.stdin

    final_status_code: int | None = None
    final_status_msg: str | None = None
    api_error_payload: str | None = None

    try:
        for raw_line in curl_stdout:
            event = parse_sse_event(raw_line.decode("utf-8", errors="replace").rstrip("\r\n"))
            if event.kind == "skip":
                continue
            if event.kind == "error":
                final_status_code, final_status_msg = event.code, event.message
                api_error_payload = event.payload
                break
            if event.kind == "final":
                if event.audio:
                    mpv_stdin.write(event.audio)
                    mpv_stdin.flush()
                break
    finally:
        with contextlib.suppress(OSError):
            mpv_stdin.close()

    curl_err = b""
    if curl_proc.stderr is not None:
        curl_err = curl_proc.stderr.read()
    curl_rc = curl_proc.wait()

    if final_status_code not in (0, None):
        print(
            f"error: MiniMax API error {final_status_code}: {final_status_msg} "
            f"(payload: {api_error_payload})",
            file=sys.stderr,
        )
        return 3
    if curl_rc != 0:
        msg = curl_err.decode(errors="replace").strip() or f"curl exit {curl_rc}"
        print(f"error: MiniMax API request failed: {msg}", file=sys.stderr)
        return 3
    return 0


class SseEvent(NamedTuple):
    kind: str  # "skip" | "error" | "final"
    audio: bytes = b""
    code: int = 0
    message: str = ""
    payload: str = ""


def parse_sse_event(line: str) -> SseEvent:
    """Parse a single SSE ``data:`` line from the MiniMax streaming endpoint.

    The MiniMax T2A v2 protocol sends progress deltas first (``status: 1``) and
    a final cumulative chunk (``status: 2``) that contains the entire MP3 from
    byte zero. Streaming deltas are reported as ``skip``; the final chunk is
    returned as ``final`` with decoded audio bytes.
    """
    if not line.startswith("data:"):
        return SseEvent(kind="skip")
    data_str = line[5:].lstrip()
    if not data_str:
        return SseEvent(kind="skip")
    try:
        obj = json.loads(data_str)
    except json.JSONDecodeError:
        return SseEvent(kind="skip")

    base = obj.get("base_resp") or {}
    code_raw = base.get("status_code")
    if code_raw is not None and code_raw != 0:
        return SseEvent(
            kind="error",
            code=int(code_raw),
            message=str(base.get("status_msg") or ""),
            payload=data_str,
        )

    data = obj.get("data") or {}
    if data.get("status") == 2:
        audio_hex = data.get("audio") or ""
        return SseEvent(kind="final", audio=bytes.fromhex(audio_hex))
    return SseEvent(kind="skip")


def speak(text: str, api_key: str) -> int:
    if not text.strip():
        print("clipboard is empty — nothing to say")
        return 0

    if len(text) > MAX_CHARS:
        print(
            f"warning: clipboard has {len(text)} chars; truncating to {MAX_CHARS}",
            file=sys.stderr,
        )
        text = text[:MAX_CHARS]

    mpv_bin = need_tool("mpv")

    payload = {
        "model": MODEL,
        "text": text,
        "stream": True,
        "voice_setting": {
            "voice_id": VOICE,
            "speed": 1,
            "vol": 1,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": SAMPLE_RATE,
            "bitrate": BITRATE,
            "format": "mp3",
        },
    }

    print(f"generating speech for {len(text)} chars…", file=sys.stderr, flush=True)

    mpv_proc = subprocess.Popen(
        [
            mpv_bin,
            "--no-terminal",
            "--no-cache",
            "--no-video",
            "--idle=no",
            "--quiet",
            "--",
            "-",
        ],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    api_rc = stream_sse_to_mpv(payload, api_key, mpv_proc)

    mpv_proc.wait()
    if mpv_proc.returncode not in (0, None):
        mpv_err = ""
        if mpv_proc.stderr is not None:
            mpv_err = mpv_proc.stderr.read().decode(errors="replace").strip()
        print(f"error: mpv playback failed: {mpv_err}", file=sys.stderr)
        return 4

    return api_rc


def main() -> int:
    api_key = load_api_key()
    text = read_clipboard()
    return speak(text, api_key)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
