#!/usr/bin/env python3
"""tts-clip — speak the current Wayland clipboard via a TTS provider.

Supports MiniMax T2A v2, OpenAI Audio Speech (also Codex), and ElevenLabs.
Reads the API key for the chosen provider from ``~/.config/tts-clip/env``
(default location, override with ``$XDG_CONFIG_HOME``) and streams the audio
straight into mpv. No file is written to disk.

Exit codes:
  0  ok (or empty clipboard, by design)
  1  unexpected error
  3  API or auth error (final status_code != 0 / HTTP error)
  4  environment / dependency missing (wl-paste, mpv, curl, key file)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, NamedTuple

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "tts-clip"
ENV_FILE = CONFIG_DIR / "env"

DEFAULT_PROVIDER = "MiniMax"
MAX_CHARS = 50_000
CURL_TIMEOUT_SEC = 300
STREAM_CHUNK = 8_192


class SseEvent(NamedTuple):
    """Result of parsing one SSE ``data:`` line from the MiniMax endpoint."""

    kind: str  # "skip" | "error" | "final"
    audio: bytes = b""
    code: int = 0
    message: str = ""
    payload: str = ""


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


def build_mini_max_payload(text: str, voice: str, model: str) -> dict[str, object]:
    return {
        "model": model,
        "text": text,
        "stream": True,
        "voice_setting": {"voice_id": voice, "speed": 1, "vol": 1, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3"},
    }


def parse_mini_max_sse(line: str) -> SseEvent:
    """Parse a single SSE ``data:`` line from the MiniMax T2A v2 stream.

    The MiniMax protocol sends progress deltas (status: 1) followed by a single
    cumulative chunk (status: 2) that contains the entire MP3 from byte zero.
    Streaming deltas are reported as ``"skip"``; the final chunk is returned
    as ``"final"`` with decoded audio bytes.
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


def stream_mini_max(
    text: str,
    voice: str,
    model: str,
    api_key: str,
    mpv_proc: subprocess.Popen[bytes],
) -> int:
    """MiniMax T2A v2 — SSE with hex-encoded MP3 chunks, write only the final chunk."""
    if mpv_proc.stdin is None:
        print("error: mpv stdin unavailable", file=sys.stderr)
        return 1
    payload = json.dumps(build_mini_max_payload(text, voice, model), ensure_ascii=False)

    curl_proc = subprocess.Popen(
        [
            "curl",
            "-sS",
            "--no-buffer",
            "-N",
            "--max-time",
            str(CURL_TIMEOUT_SEC),
            "--fail-with-body",
            "-X",
            "POST",
            "https://api.minimax.io/v1/t2a_v2",
            "-H",
            f"Authorization: Bearer {api_key}",
            "-H",
            "Content-Type: application/json",
            "-d",
            payload,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if curl_proc.stdout is None:
        print("error: curl stdout unavailable", file=sys.stderr)
        return 1

    final_code: int | None = None
    final_msg: str | None = None
    final_payload: str | None = None

    try:
        for raw_line in curl_proc.stdout:
            ev = parse_mini_max_sse(raw_line.decode("utf-8", errors="replace").rstrip("\r\n"))
            if ev.kind == "skip":
                continue
            if ev.kind == "error":
                final_code, final_msg, final_payload = ev.code, ev.message, ev.payload
                break
            if ev.kind == "final":
                if ev.audio:
                    mpv_proc.stdin.write(ev.audio)
                    mpv_proc.stdin.flush()
                break
    finally:
        with contextlib.suppress(OSError):
            mpv_proc.stdin.close()

    curl_err = curl_proc.stderr.read() if curl_proc.stderr else b""
    curl_rc = curl_proc.wait()

    if final_code not in (0, None):
        print(
            f"error: MiniMax API error {final_code}: {final_msg} (payload: {final_payload})",
            file=sys.stderr,
        )
        return 3
    if curl_rc != 0:
        msg = curl_err.decode(errors="replace").strip() or f"curl exit {curl_rc}"
        print(f"error: MiniMax request failed: {msg}", file=sys.stderr)
        return 3
    return 0


def build_openai_payload(text: str, voice: str, model: str) -> dict[str, object]:
    return {"model": model, "input": text, "voice": voice, "response_format": "mp3"}


def stream_openai(
    text: str,
    voice: str,
    model: str,
    api_key: str,
    mpv_proc: subprocess.Popen[bytes],
) -> int:
    """OpenAI Audio Speech — raw binary MP3, no streaming protocol."""
    if mpv_proc.stdin is None:
        print("error: mpv stdin unavailable", file=sys.stderr)
        return 1
    payload = json.dumps(build_openai_payload(text, voice, model), ensure_ascii=False)
    return _stream_binary(
        curl_args=[
            "curl",
            "-sS",
            "--no-buffer",
            "--max-time",
            str(CURL_TIMEOUT_SEC),
            "--fail-with-body",
            "-X",
            "POST",
            "https://api.openai.com/v1/audio/speech",
            "-H",
            f"Authorization: Bearer {api_key}",
            "-H",
            "Content-Type: application/json",
            "-d",
            payload,
        ],
        mpv_proc=mpv_proc,
        provider_label="OpenAI",
    )


def build_elevenlabs_payload(text: str, voice: str, model: str) -> dict[str, object]:
    # For ElevenLabs, ``voice`` is a voice_id, not a name.
    return {
        "text": text,
        "model_id": model,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.5},
    }


def stream_elevenlabs(
    text: str,
    voice: str,
    model: str,
    api_key: str,
    mpv_proc: subprocess.Popen[bytes],
) -> int:
    """ElevenLabs — raw binary MP3, voice_id from CLI/env (e.g. ``21m00Tcm4TlvDq8ikWAM``)."""
    if mpv_proc.stdin is None:
        print("error: mpv stdin unavailable", file=sys.stderr)
        return 1
    payload = json.dumps(build_elevenlabs_payload(text, voice, model), ensure_ascii=False)
    return _stream_binary(
        curl_args=[
            "curl",
            "-sS",
            "--no-buffer",
            "--max-time",
            str(CURL_TIMEOUT_SEC),
            "--fail-with-body",
            "-X",
            "POST",
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
            "-H",
            f"xi-api-key: {api_key}",
            "-H",
            "Content-Type: application/json",
            "-H",
            "Accept: audio/mpeg",
            "-d",
            payload,
        ],
        mpv_proc=mpv_proc,
        provider_label="ElevenLabs",
    )


def _stream_binary(
    curl_args: list[str],
    mpv_proc: subprocess.Popen[bytes],
    provider_label: str,
) -> int:
    """Run curl, stream stdout chunks into mpv's stdin. Return exit code.

    Used by OpenAI / ElevenLabs, whose endpoints return a single binary body
    (no SSE). Reading in chunks lets mpv start playing as soon as the first
    bytes hit its stdin; the pipe acts as flow control.
    """
    curl_proc = subprocess.Popen(curl_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if curl_proc.stdout is None or mpv_proc.stdin is None:
        print(f"error: failed to open pipes for {provider_label}", file=sys.stderr)
        return 1

    mpv_stdin = mpv_proc.stdin
    try:
        while True:
            chunk = curl_proc.stdout.read(STREAM_CHUNK)
            if not chunk:
                break
            mpv_stdin.write(chunk)
    except (OSError, ValueError):
        # mpv closed its stdin (e.g. user killed it); stop pumping
        pass
    finally:
        with contextlib.suppress(OSError):
            mpv_stdin.close()

    curl_err = curl_proc.stderr.read() if curl_proc.stderr else b""
    curl_rc = curl_proc.wait()
    if curl_rc != 0:
        msg = curl_err.decode(errors="replace").strip() or f"curl exit {curl_rc}"
        print(f"error: {provider_label} request failed: {msg}", file=sys.stderr)
        return 3
    return 0


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------


class ProviderInfo(NamedTuple):
    name: str
    env_key: str
    default_voice: str
    default_model: str
    description: str
    key_url: str
    stream_fn: Callable[..., int]


PROVIDERS: dict[str, ProviderInfo] = {
    "MiniMax": ProviderInfo(
        name="MiniMax",
        env_key="MiniMax_API_KEY",
        default_voice="English_Graceful_Lady",
        default_model="speech-02-turbo",
        description="MiniMax T2A v2 — many natural voices, generous free tier",
        key_url="https://MiniMax.io",
        stream_fn=stream_mini_max,
    ),
    "openai": ProviderInfo(
        name="openai",
        env_key="OPENAI_API_KEY",
        default_voice="alloy",
        default_model="tts-1",
        description="OpenAI Audio Speech — also used by Codex",
        key_url="https://platform.openai.com/api-keys",
        stream_fn=stream_openai,
    ),
    "elevenlabs": ProviderInfo(
        name="elevenlabs",
        env_key="ELEVENLABS_API_KEY",
        default_voice="21m00Tcm4TlvDq8ikWAM",  # "Rachel"
        default_model="eleven_monolingual_v1",
        description="ElevenLabs — premium neural voices, voice cloning",
        key_url="https://elevenlabs.io",
        stream_fn=stream_elevenlabs,
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_env(env_file: Path) -> dict[str, str]:
    """Parse the env file into a dict. Returns ``{}`` if the file is missing.

    Keys must match ``[A-Za-z_][A-Za-z0-9_]*`` (standard env var syntax);
    anything else is treated as a comment and skipped silently.
    """
    if not env_file.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            continue
        out[key] = val.strip().strip('"').strip("'")
    return out


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
        print(f"error: wl-paste failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(4)
    return result.stdout


def list_providers() -> None:
    print("Available TTS providers:")
    print()
    for name, info in PROVIDERS.items():
        marker = " (default)" if name == DEFAULT_PROVIDER else ""
        print(f"  {name}{marker}")
        print(f"    env var:       {info.env_key}")
        print(f"    default voice: {info.default_voice}")
        print(f"    default model: {info.default_model}")
        print(f"    description:   {info.description}")
        print(f"    get a key at:  {info.key_url}")
        print()
    print("Note: Anthropic (Claude) does not provide a TTS API.")
    print("Use 'openai' for the closest equivalent (also covers Codex).")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tts-clip",
        description="Speak the Wayland clipboard via a TTS provider.",
    )
    parser.add_argument(
        "--provider",
        "-p",
        choices=list(PROVIDERS.keys()),
        help="TTS provider to use (default: $TTS_PROVIDER or 'MiniMax')",
    )
    parser.add_argument(
        "--voice",
        "-V",
        help="Override the default voice for the chosen provider",
    )
    parser.add_argument(
        "--model",
        "-m",
        help="Override the default model for the chosen provider",
    )
    parser.add_argument(
        "--list-providers",
        action="store_true",
        help="List available providers and exit",
    )
    return parser.parse_args(argv)


def _resolve_provider(args: argparse.Namespace, env: dict[str, str]) -> ProviderInfo | None:
    provider_name = args.provider or env.get("TTS_PROVIDER", DEFAULT_PROVIDER)
    if provider_name not in PROVIDERS:
        print(f"error: unknown provider '{provider_name}'", file=sys.stderr)
        print(f"  known providers: {', '.join(PROVIDERS.keys())}", file=sys.stderr)
        print("  run `tts-clip --list-providers` for details", file=sys.stderr)
        return None
    provider = PROVIDERS[provider_name]
    api_key = env.get(provider.env_key, "")
    if not api_key or "PASTE-NEW-KEY-HERE" in api_key:
        print(f"error: {provider.env_key} not set in {ENV_FILE}", file=sys.stderr)
        print(f"  hint: get a key at {provider.key_url}", file=sys.stderr)
        print(
            f"  then add a line to {ENV_FILE}:  {provider.env_key}=<your-key>",
            file=sys.stderr,
        )
        return None
    return provider


def _resolve_voice_model(
    args: argparse.Namespace, env: dict[str, str], provider: ProviderInfo
) -> tuple[str, str]:
    upper = provider.name.upper()
    voice = args.voice or env.get(f"{upper}_VOICE", provider.default_voice)
    model = args.model or env.get(f"{upper}_MODEL", provider.default_model)
    return voice, model


def _run_mpv(text: str, provider: ProviderInfo, voice: str, model: str, api_key: str) -> int:
    """Start mpv, run the provider's stream_fn, then return the right exit code."""
    mpv_bin = need_tool("mpv")
    print(
        f"speaking {len(text)} chars with {provider.name} (voice={voice}, model={model})…",
        file=sys.stderr,
        flush=True,
    )
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
    api_rc = provider.stream_fn(text, voice, model, api_key, mpv_proc)
    mpv_proc.wait()

    if api_rc != 0:
        return api_rc
    if mpv_proc.returncode not in (0, None):
        mpv_err = ""
        if mpv_proc.stderr is not None:
            mpv_err = mpv_proc.stderr.read().decode(errors="replace").strip()
        print(f"error: mpv playback failed: {mpv_err}", file=sys.stderr)
        return 4
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.list_providers:
        list_providers()
        return 0

    env = load_env(ENV_FILE)
    provider = _resolve_provider(args, env)
    if provider is None:
        return 3
    voice, model = _resolve_voice_model(args, env, provider)

    text = read_clipboard()
    if not text.strip():
        print("clipboard is empty — nothing to say")
        return 0
    if len(text) > MAX_CHARS:
        print(
            f"warning: clipboard has {len(text)} chars; truncating to {MAX_CHARS}",
            file=sys.stderr,
        )
        text = text[:MAX_CHARS]

    return _run_mpv(text, provider, voice, model, env[provider.env_key])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
