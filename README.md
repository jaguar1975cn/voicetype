# voicetype

Local push-to-talk dictation for GNOME/Wayland. Mixed Chinese + English in a
single utterance, no cloud, no API key.

## How it works

    Super+Z ──▶ voicetype-toggle ──▶ pw-record ──▶ recording.wav
       (again)        │
                      ├─▶ unix socket ─▶ voicetype daemon (Whisper in VRAM) ─▶ text
                      └─▶ wl-copy ──▶ ydotool ctrl+v ──▶ focused window

A `systemd --user` daemon holds Whisper `large-v3-turbo` resident so the
hotkey does not pay the model load on every use. It is pinned to the RTX 3050
via `CUDA_VISIBLE_DEVICES`, leaving the RTX 5080 free.

Language is auto-detected per utterance rather than fixed, which is what
code-switched speech ("把这个 function 重构一下") needs.

## Keys

| Key | Action |
|---|---|
| `Super+Z` | start / stop dictation, paste with Ctrl+V |
| `Shift+Super+Z` | same, but pastes with Ctrl+Shift+V (terminals) |

Press once to start (rising beep), speak, press again (falling beep) to insert.
`Super+Space` is left alone — that is the ibus input-source switcher.

## Why the clipboard, not synthetic keystrokes

Typing CJK through `/dev/uinput` needs live keymap remapping and is unreliable.
The text goes on the clipboard and a paste shortcut is pressed instead; the
previous clipboard contents are restored ~1.2s later. Consequence: a paste
shortcut must exist in the target app, and terminals need the second hotkey.

## Config

`~/.config/voicetype/config.toml`. After changing `model` or `gpu`:

    systemctl --user restart voicetype

`source` pins the microphone by PipeWire `node.name`, so changing the system
default input — or a bluetooth headset connecting — cannot silently move
dictation to another mic. List candidates with:

    pw-cli ls Node | grep -B2 'Audio/Source'

Other useful knobs: `initial_prompt` biases jargon and names;
`halfwidth_punctuation` converts ，。？！ to ASCII; `max_seconds` caps a
forgotten recording (the capped audio is still transcribed on the next press).

## Commands

    voicetype-toggle [toggle|start|stop|cancel|status]
    voicetype-toggle --paste-key ctrl+shift+v
    voicetype-record-fixture <name> [seconds]

## Tests

    cd ~/work/ai/test/voice-typing
    ./venv/bin/python -m pytest tests/ -q          # all
    ./venv/bin/python -m pytest tests/ -q -m "not slow"   # no GPU needed

`tests/test_transcribe.py` needs the daemon running. The code-switched test
needs a real recording — see `tests/fixtures/README.md`; espeak-ng's Mandarin
is too synthetic for Whisper to decode, so it cannot be generated.

## Troubleshooting

| Symptom | Check |
|---|---|
| "Daemon unreachable" | `systemctl --user status voicetype`, `journalctl --user -u voicetype -n 50` |
| "ydotool failed" | `systemctl --user status ydotoold`; is your user in the `input` group? (`id -nG`) |
| Nothing pastes, text is on clipboard | target app has no Ctrl+V; use `Shift+Super+Z` |
| CUDA out of memory | another process is on the pinned GPU: `nvidia-smi` |
| Wrong language picked | set `language = "zh"` or `"en"` if you stop code-switching |
| Recording is silent | wrong mic: check `source` against `wpctl status`, and `pactl get-source-mute <name>` |

### Note on cudaSetDevice

The daemon pins its GPU with `CUDA_VISIBLE_DEVICES`, not CTranslate2's
`device_index=`. `cudaSetDevice` is per-thread state, so a request arriving on
a fresh handler thread reverts to device 0 and allocates its workspace on the
wrong card. Hiding the other GPUs is the only reliable fix. Do not "simplify"
this back to `device_index=`.
