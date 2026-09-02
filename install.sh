#!/usr/bin/env bash
set -euo pipefail

PLUGIN_DIR="$HOME/.config/omarchy/plugins/io.github.djspatule.tts-clip"
SCRIPT_SRC="$PLUGIN_DIR/tts_clip.py"
SCRIPT_BIN="$HOME/.local/bin/tts-clip"
ENV_DIR="$HOME/.config/tts-clip"
ENV_FILE="$ENV_DIR/env"

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

have wl-paste || die "wl-clipboard is required (sudo pacman -S wl-clipboard)"
have mpv      || die "mpv is required (sudo pacman -S mpv)"
have curl     || die "curl is required"
have python3  || die "python3 is required"

mkdir -p "$HOME/.local/bin" "$ENV_DIR"

if [[ ! -f "$SCRIPT_SRC" ]]; then
  die "expected $SCRIPT_SRC — install the Omarchy plugin first:
  omarchy plugin add https://github.com/djspatule/tts-clip --enable"
fi

chmod +x "$SCRIPT_SRC"
ln -sf "$SCRIPT_SRC" "$SCRIPT_BIN"
printf 'linked %s -> %s\n' "$SCRIPT_BIN" "$SCRIPT_SRC"

# Read existing env into a temp file so we can rewrite cleanly.
TMP_ENV="$(mktemp)"
trap 'rm -f "$TMP_ENV"' EXIT
if [[ -f "$ENV_FILE" ]]; then
  cp "$ENV_FILE" "$TMP_ENV"
fi

# Pick provider (skip if already set)
provider=""
if grep -qE '^TTS_PROVIDER=' "$TMP_ENV" 2>/dev/null; then
  provider=$(grep -E '^TTS_PROVIDER=' "$TMP_ENV" | head -n1 | cut -d= -f2-)
fi

if [[ -z "$provider" ]]; then
  cat <<PROMPT

Which TTS provider do you want to use?
  1) MiniMax      (default; many natural voices, free tier)
  2) openai       (also covers Codex; needs OPENAI_API_KEY)
  3) elevenlabs   (premium neural voices; needs ELEVENLABS_API_KEY)
PROMPT
  read -r -p "choice [1]: " choice
  case "${choice:-1}" in
    1|"") provider="MiniMax" ;;
    2)    provider="openai"  ;;
    3)    provider="elevenlabs" ;;
    *)    die "invalid choice: $choice" ;;
  esac
fi

# Map provider → env var name + key-acquisition URL
case "$provider" in
  MiniMax)
    env_key="MiniMax_API_KEY"
    key_url="https://MiniMax.io"
    ;;
  openai)
    env_key="OPENAI_API_KEY"
    key_url="https://platform.openai.com/api-keys"
    ;;
  elevenlabs)
    env_key="ELEVENLABS_API_KEY"
    key_url="https://elevenlabs.io"
    ;;
  *)
    die "unknown provider '$provider' (must be MiniMax, openai, or elevenlabs)"
    ;;
esac

# Prompt for the API key if not already set or still placeholder.
current_key=$(grep -E "^${env_key}=" "$TMP_ENV" 2>/dev/null | head -n1 | cut -d= -f2- || true)
if [[ -z "$current_key" || "$current_key" == "PASTE-NEW-KEY-HERE" ]]; then
  cat <<PROMPT

Set up your $provider API key.
Get one at: $key_url
PROMPT
  read -r -p "paste your $env_key: " new_key
  [[ -n "$new_key" ]] || die "no key provided"
  current_key="$new_key"
fi

# Write env file (clean rewrite). Preserve any unrelated keys the user had.
umask 077
{
  echo "# tts-clip env — managed by install.sh"
  echo "# See https://github.com/djspatule/tts-clip for details."
  echo "# Switch providers by editing TTS_PROVIDER; unused *_API_KEY lines"
  echo "# are kept so you can flip back without re-entering them."
  echo
  echo "TTS_PROVIDER=$provider"
  echo "$env_key=$current_key"
  # Preserve any other KEY=... lines (e.g. the user's other provider keys).
  awk -F= -v keep="$env_key" '
    /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
    /^TTS_PROVIDER=/ { next }
    /^[[:space:]]*[^=]+=/ {
      k = $1; sub(/^[[:space:]]+/, "", k); sub(/[[:space:]]+$/, "", k)
      if (k != keep) print
    }
  ' "$TMP_ENV" 2>/dev/null || true
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"

cat <<DONE

done. env file:
  $ENV_FILE (mode 600)

try it:
  echo "hello world" | wl-copy && tts-clip
or click the 🔊 bar widget.

switch providers later by editing TTS_PROVIDER in $ENV_FILE.
DONE
