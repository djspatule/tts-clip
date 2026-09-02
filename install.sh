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
  die "expected $SCRIPT_SRC — is the Omarchy plugin installed? run: omarchy plugin add https://github.com/djspatule/tts-clip --enable"
fi

chmod +x "$SCRIPT_SRC"

if [[ ! -e "$SCRIPT_BIN" || "$SCRIPT_BIN" -ef "$SCRIPT_SRC" ]] || readlink "$SCRIPT_BIN" 2>/dev/null | grep -qv "$(basename "$SCRIPT_SRC")$"; then
  ln -sf "$SCRIPT_SRC" "$SCRIPT_BIN"
  printf 'linked %s -> %s\n' "$SCRIPT_BIN" "$SCRIPT_SRC"
fi

need_key=1
if [[ -f "$ENV_FILE" ]]; then
  current=$(grep -E '^MiniMax_API_KEY=' "$ENV_FILE" | head -n1 | cut -d= -f2-)
  if [[ -n "$current" && "$current" != PASTE-NEW-KEY-HERE ]]; then
    need_key=0
  fi
fi

if [[ "$need_key" -eq 1 ]]; then
  printf '\nMiniMax TTS API key is needed (get one at https://MiniMax.io).\n'
  read -r -p "paste your MiniMax API key (sk-cp-...): " key
  [[ -n "$key" ]] || die "no key provided"
  umask 077
  printf 'MiniMax_API_KEY=%s\n' "$key" > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  printf 'wrote %s (mode 600)\n' "$ENV_FILE"
fi

cat <<EOF

done. try it now:
  echo "hello world" | wl-copy && tts-clip
or click the speaker (\xF0\x9F\x94\x8A) icon in your bar.
EOF
