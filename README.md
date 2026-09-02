# tts-clip

> Click the speaker in your Omarchy bar (or hit your keybind) and have your clipboard read back to you in a natural neural voice.

`tts-clip` is a tiny CLI + Omarchy bar-widget plugin that speaks whatever is on your Wayland clipboard using the [MiniMax T2A v2](https://MiniMax.io) text-to-speech API. No audio file is written to disk — speech streams directly into `mpv`.

![Bar widget icon](preview.png)

## Why

Sometimes you want your eyes to stay on something else: a long article, a coding session, an email. Select the text, press a hotkey, keep working.

## Features

- One-click TTS from the Omarchy bar
- Streams hex-encoded MP3 chunks directly to `mpv` (no temp files)
- Handles long text (up to ~50 000 chars; the API is the bottleneck, not the script)
- Empty clipboard is detected and reported, no API call wasted
- Errors surface clearly (auth, network, missing tools)
- Works on any Wayland + Hyprland desktop, not just Omarchy

## Requirements

| Tool           | Why                          | Install                          |
| -------------- | ---------------------------- | -------------------------------- |
| `python3` ≥3.9 | script runtime               | `sudo pacman -S python`          |
| `wl-clipboard` | read Wayland clipboard       | `sudo pacman -S wl-clipboard`    |
| `mpv`          | audio playback               | `sudo pacman -S mpv`             |
| `curl`         | HTTP client used by script   | already on Arch                  |
| `MiniMax` API key | TTS provider              | get one at [MiniMax.io](https://MiniMax.io) |

## Install (Omarchy, recommended)

```sh
omarchy plugin add https://github.com/djspatule/tts-clip --enable
./install.sh
```

The plugin command clones this repo into `~/.config/omarchy/plugins/io.github.djspatule.tts-clip/`. `install.sh` symlinks `tts-clip.py` into `~/.local/bin/tts-clip` and stores your MiniMax API key at `~/.config/tts-clip/env` (mode 600).

## Install (manual, any Wayland desktop)

```sh
git clone https://github.com/djspatule/tts-clip ~/.local/share/tts-clip
ln -sf ~/.local/share/tts-clip/tts-clip.py ~/.local/bin/tts-clip
chmod +x ~/.local/bin/tts-clip
mkdir -p ~/.config/tts-clip
echo "MiniMax_API_KEY=sk-cp-YOUR-KEY-HERE" > ~/.config/tts-clip/env
chmod 600 ~/.config/tts-clip/env
```

Add a Hyprland binding (any key you like):

```ini
bind = SUPER SHIFT, V, exec, tts-clip
```

Reload Hyprland (`Super+Esc` → "Reload Hyprland" or `hyprctl reload`) and the binding is live.

## Usage

- **Click the speaker icon in the bar** (default section: right) — or
- **Press your keybind** after selecting text — or
- **From a terminal**:
  ```sh
  echo "hello world" | wl-copy && tts-clip
  ```

While audio is being generated, `tts-clip` prints `generating speech for N chars…` to stderr.

## Configuration

Two constants live near the top of `tts-clip.py`:

| Constant           | Default                | Purpose                                  |
| ------------------ | ---------------------- | ---------------------------------------- |
| `MODEL`            | `speech-02-turbo`      | Cheap, fast, natural. Try `speech-01-turbo` or `speech-02` for other voices/qualities. |
| `VOICE`            | `English_Graceful_Lady` | Any voice id from `GET /v1/voice/list`   |
| `SAMPLE_RATE`      | `32000`                | Hz                                       |
| `BITRATE`          | `128000`               | bps                                      |
| `MAX_CHARS`        | `50000`                | Truncation guard; raise if you need more |
| `CURL_TIMEOUT_SEC` | `300`                  | Generation timeout for very long text    |

To use a different voice, edit `VOICE` (or extend the script to accept `--voice`).

## How it works

1. `wl-paste --no-newline` reads clipboard text (or the script exits cleanly if empty).
2. `curl` POSTs to `https://api.minimax.io/v1/t2a_v2` with the nested `voice_setting` / `audio_setting` schema, `stream: true`.
3. MiniMax returns Server-Sent Events; each `data: {...}` line has a hex-encoded MP3 chunk in `data.audio`. The first six chunks are deltas for progress reporting; the chunk with `status: 2` contains the **complete** audio (same ID3 header as chunk 0). Earlier versions of this script wrote every chunk, which is why it sounded like it was repeating — the final cumulative chunk is now the only one piped to `mpv`.
4. Hex is decoded and piped to `mpv --no-terminal --idle=no --no-video --quiet -- -`. `--idle=no` is required so `mpv` exits at EOF instead of waiting for more input.
5. `mpv_proc.wait()` blocks until playback ends; exit code is propagated.

## Security

- The API key never appears in `ps` output — only inside the curl command's `-H "Authorization: Bearer …"` argument for the duration of the request.
- The env file is created with mode `0600` by `install.sh`.
- The script never writes the audio to disk.
- The script makes a single outbound HTTPS request to `api.minimax.io`; no other network activity.

## License

MIT. See [LICENSE](LICENSE).

## Contributing

Issues and PRs welcome at <https://github.com/djspatule/tts-clip>.

## Marketplace

This plugin is intended for the [Omarchy Plugin Marketplace](https://plugins.omarchy.org/); submission tracked in the marketplace repo.
