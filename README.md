# tts-clip

> Click the 🔊 icon in your Omarchy bar (or hit your keybind) and have your clipboard read back to you in a natural neural voice.

`tts-clip` is a tiny CLI + Omarchy bar-widget plugin that speaks whatever is on your Wayland clipboard. It ships with three TTS providers — **MiniMax**, **OpenAI** (also used by Codex), and **ElevenLabs** — and you bring your own API key.

![Bar widget icon](preview.png)

## Features

- One-click TTS from the Omarchy bar
- Three providers out of the box: MiniMax, OpenAI, ElevenLabs
- Streams audio straight to `mpv` — no temp file
- Handles long text (up to ~50 000 chars)
- Empty clipboard is detected, no API call wasted
- Clear error messages (auth, network, missing tools)
- Works on any Wayland + Hyprland desktop, not just Omarchy

## Quickstart (Omarchy)

```sh
omarchy plugin add https://github.com/djspatule/tts-clip --enable
~/.config/omarchy/plugins/io.github.djspatule.tts-clip/install.sh
```

`install.sh` will:
1. Check that `wl-clipboard`, `mpv`, `curl`, and `python3` are installed (and tells you what to install if not).
2. Ask which provider you want.
3. Ask for the matching API key.
4. Write it all to `~/.config/tts-clip/env` (mode `0600`).
5. Symlink `tts_clip.py` → `~/.local/bin/tts-clip`.

Then copy some text and:
- click the 🔊 icon in the bar, or
- press your Hyprland keybind (`Super+Shift+V` if you added the one from earlier versions).

## Getting an API key

The script reads from one file: `~/.config/tts-clip/env`. Format is one `KEY=value` per line, `#` for comments:

```sh
# ~/.config/tts-clip/env
#
# which provider to use (one of: MiniMax, openai, elevenlabs)
TTS_PROVIDER=MiniMax

# MiniMax — get one at https://MiniMax.io
MiniMax_API_KEY=sk-cp-YOUR-KEY-HERE

# OpenAI / Codex — get one at https://platform.openai.com/api-keys
# OPENAI_API_KEY=sk-YOUR-KEY-HERE

# ElevenLabs — get one at https://elevenlabs.io
# ELEVENLABS_API_KEY=YOUR-KEY-HERE
```

`install.sh` creates this for you. To change providers or add another key, just edit the file. Keep it mode `0600`.

### Providers at a glance

| Provider      | API key env var       | Where to get a key                                       | Default voice          | Default model                |
| ------------- | --------------------- | -------------------------------------------------------- | ---------------------- | ---------------------------- |
| `MiniMax` (default) | `MiniMax_API_KEY`     | [MiniMax.io](https://MiniMax.io)                              | `English_Graceful_Lady` | `speech-02-turbo`            |
| `openai` (also Codex) | `OPENAI_API_KEY`      | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | `alloy`                | `tts-1`                      |
| `elevenlabs`  | `ELEVENLABS_API_KEY`  | [elevenlabs.io](https://elevenlabs.io)                    | `21m00Tcm4TlvDq8ikWAM` (Rachel) | `eleven_monolingual_v1` |

Run `tts-clip --list-providers` for the full up-to-date list with voices & models.

### About Anthropic / Claude

Anthropic does **not** provide a text-to-speech API. If your Claude subscription is your only key, you'll still need an OpenAI key (or another supported provider) for `tts-clip`. Use `--provider openai` as the closest alternative — it covers both OpenAI Audio Speech and Codex.

## Switching providers at runtime

```sh
# one-off via flag (no env change)
tts-clip --provider openai --voice nova

# change the default in your env file
sed -i 's/^TTS_PROVIDER=.*/TTS_PROVIDER=openai/' ~/.config/tts-clip/env
```

Per-provider voice and model overrides also work via env: `OPENAI_VOICE`, `OPENAI_MODEL`, `ELEVENLABS_VOICE`, `ELEVENLABS_MODEL`, etc.

## Manual install (any Wayland + Hyprland desktop)

Skip the Omarchy plugin path and use the CLI directly:

```sh
git clone https://github.com/djspatule/tts-clip ~/.local/share/tts-clip
ln -sf ~/.local/share/tts-clip/tts_clip.py ~/.local/bin/tts-clip
chmod +x ~/.local/bin/tts-clip

mkdir -p ~/.config/tts-clip
cat > ~/.config/tts-clip/env <<'EOF'
TTS_PROVIDER=MiniMax
MiniMax_API_KEY=sk-cp-YOUR-KEY-HERE
EOF
chmod 600 ~/.config/tts-clip/env
```

Add a Hyprland binding (in `~/.config/hypr/bindings.lua`):

```lua
o.bind("SUPER + SHIFT + V", "Speak clipboard", "tts-clip")
```

Then `hyprctl reload`.

## CLI flags

```
usage: tts-clip [-h] [--provider {MiniMax,openai,elevenlabs}]
                [--voice VOICE] [--model MODEL] [--list-providers]
```

| Flag | What it does |
| --- | --- |
| `--provider`, `-p` | Pick a provider for this invocation only |
| `--voice`, `-V` | Override the default voice |
| `--model`, `-m` | Override the default model |
| `--list-providers` | Show providers + their env vars + where to get a key |

## Requirements

| Tool         | Why                          | Install                                       |
| ------------ | ---------------------------- | --------------------------------------------- |
| `python3` ≥ 3.10 | runtime                  | `sudo pacman -S python`                       |
| `wl-clipboard` | read Wayland clipboard     | `sudo pacman -S wl-clipboard`                 |
| `mpv`         | audio playback              | `sudo pacman -S mpv`                          |
| `curl`        | HTTP client                 | already on Arch                               |

## How it works

1. `wl-paste --no-newline` reads the clipboard (exits cleanly if empty).
2. The selected provider's TTS endpoint is called via `curl`:
   - **MiniMax** (`/v1/t2a_v2`): returns SSE with hex-encoded MP3 chunks. Only the final cumulative chunk (`status: 2`) is piped to `mpv` — the streaming deltas are progress metadata, not actual audio (writing them caused the "repeats twice" bug in earlier versions).
   - **OpenAI** (`/v1/audio/speech`): returns raw MP3 binary, streamed straight to `mpv`.
   - **ElevenLabs** (`/v1/text-to-speech/{voice_id}`): returns raw MP3 binary, streamed straight to `mpv`.
3. `mpv --idle=no` exits at EOF.

## Security

- API keys are read from `~/.config/tts-clip/env` (mode `0600`), never embedded in the script or repo.
- `gitleaks` and a `test_no_secrets_in_*` test enforce this in CI for the manifest, install.sh, and Python source.
- One outbound HTTPS request per invocation to your chosen provider. No other network activity.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issues and PRs welcome at <https://github.com/djspatule/tts-clip>.

## Marketplace

Listed at <https://github.com/omacom/omarchy-plugin-marketplace/issues/4344>.
