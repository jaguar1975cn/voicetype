# voicetype

Local push-to-talk dictation for GNOME/Wayland. Mixed Chinese + English in a
single utterance, no cloud, no API key, no audio leaves the machine.

Press a hotkey, speak, press again — the text lands in whatever window has
focus.

## Requirements

- **GNOME on Wayland.** The paste path is built for Mutter, which does not
  implement the virtual-keyboard protocol (so `wtype` cannot work). Other
  compositors need a different insertion method.
- **An NVIDIA GPU**, ~2GB free VRAM for the default model. There is no CPU
  fallback.
- **Python 3.12** — faster-whisper's dependency wheels. Or just
  [uv](https://github.com/astral-sh/uv), which fetches its own interpreter;
  `install.sh` uses it when present.
- **PipeWire** (`pw-record`), `wl-clipboard`, `libnotify`, and `ydotool`.

| Distro | Command |
|---|---|
| Fedora | `sudo dnf install pipewire-utils wl-clipboard libnotify` |
| Debian / Ubuntu | `sudo apt install pipewire-bin wl-clipboard libnotify-bin` |
| Arch | `sudo pacman -S pipewire wl-clipboard libnotify` |
| openSUSE | `sudo zypper install pipewire-tools wl-clipboard libnotify-tools` |

`ydotool` is installed by `install-root.sh`, which handles all four. Run
`install.sh` on any other distro and it will name the missing commands so you
can map them yourself.

Only Fedora 43 is tested on real hardware — the other package names come from
each distro's index. If one is wrong, please open an issue.

## Install

    git clone https://github.com/jaguar1975cn/voicetype && cd voicetype
    sudo ./install-root.sh      # ydotool + /dev/uinput access
    #   log out and back in for the group change
    ./install.sh                # venv, commands, services, hotkeys

`install.sh` is safe to re-run; it will not overwrite an existing config or
disturb keyboard shortcuts you already have. It creates a venv in
`~/.local/share/voicetype/venv` and installs this repo into it in editable
mode, so the checkout stays the source of truth.

The model (~1.6GB) downloads on the daemon's first start. Watch it with:

    journalctl --user -u voicetype -f

**What `install-root.sh` does, and why it matters:** it adds a udev rule making
`/dev/uinput` writable by the `input` group and adds you to that group. This
lets any process running as you synthesise keystrokes system-wide. That is
inherent to keystroke injection on Wayland, not specific to this tool, but it
is a real reduction in isolation — read the script before running it.

## How it works

    Super+Z ──▶ voicetype-toggle ──▶ pw-record ──▶ recording.wav
       (again)        │
                      ├─▶ unix socket ─▶ voicetype daemon (Whisper in VRAM) ─▶ text
                      └─▶ wl-copy ──▶ ydotool ctrl+v ──▶ focused window

A `systemd --user` daemon holds Whisper `large-v3-turbo` resident so the
hotkey does not pay the ~10-20s model load on every use. On a multi-GPU box,
set `gpu` in the config to pin it to one card via `CUDA_VISIBLE_DEVICES` and
keep it off whatever else is using the GPU.

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

    ~/.local/share/voicetype/venv/bin/python -m pytest tests/ -q
    ~/.local/share/voicetype/venv/bin/python -m pytest tests/ -q -m "not slow"

The second form needs no GPU and no daemon. `tests/test_transcribe.py` needs
the daemon running.

The code-switched test needs a recording of your own voice, which is
deliberately not in this repo — recordings are personal data. Make one with
`voicetype-record-fixture mixed_zh_en` (see `tests/fixtures/README.md` for the
phrase); the test skips while it is absent. espeak-ng's Mandarin is too
synthetic for Whisper to decode, so it cannot be synthesised.

## Suspend / resume

The daemon holds a CUDA context across sleep. NVIDIA only survives that if
it can snapshot video memory at suspend (`NVreg_PreserveVideoMemoryAllocations=1`
plus the `nvidia-suspend`/`nvidia-resume` units), which needs free space at
`NVreg_TemporaryFilePath` (and disk-backed swap — zram does not count) of at
least total VRAM across all GPUs. When the save fails, the resume leaves every
context attached to dead video memory; the daemon's next transcribe then
blocks in an uninterruptible ioctl inside the driver. That stage is not
killable — SIGKILL included — and the corpse pins its VRAM until reboot.
Check with:

    grep -iE 'Preserve|TemporaryFilePath' /proc/driver/nvidia/params
    df /var/tmp                      # must exceed combined VRAM
    swapon --show                    # zram-only swap is not enough

On top of that requirement, `install-root.sh` installs two system units
(wired in `contrib/`) that stop the daemon before the driver snapshots VRAM
and start it after resume. The stop must be ordered `Before=nvidia-suspend.service`
— a stock `/usr/lib/systemd/system-sleep` hook runs *after* that snapshot,
which is too late — so these are units, not hooks. With them installed, a bad
GPU save can no longer wedge this service: the ~2s model reload after resume
replaces the context. Anything outside your user services still rides out
the save; fix the capacity above for those.

Extra GPU daemons join via `/etc/default/voicetype-sleep`:

    EXTRA_UNITS="qwen.service"      # e.g. a llama.cpp server

Enabled units are stopped before every suspend and restarted after resume
(first request after resume waits out the model load). A *disabled* unit
that happens to be running is also stopped — that is what saves it — but
only restarted when the hook itself stopped it, so a deliberately stopped
service stays stopped.

## Known limits

An isolated English word inside an otherwise Chinese sentence is occasionally
transliterated into same-sounding hanzi rather than kept as English — observed
with "把这个 function 重构一下" coming out as "把这个方形重构一下".

This is per-word acoustics, not a general failure: forcing `language=en` on
that same audio returns "Re-enable the function", so the word was recognised;
the zh segment decoder then mapped it onto matching characters. Terms with
distinctive pronunciation (API, response, cache) survive reliably, with or
without `initial_prompt`. Neither a bigger model (large-v3 behaves the same as
turbo here) nor a code-switching prompt changes it, so don't spend time
tuning those — say the word more distinctly, or edit the one word afterwards.

## Troubleshooting

| Symptom | Check |
|---|---|
| "Daemon unreachable" | `systemctl --user status voicetype`, `journalctl --user -u voicetype -n 50` |
| Press again → no paste, error only ~30s later | nvidia driver wedge on the pinned GPU: journal shows `transcription wedged`; the daemon kills itself and systemd restarts it — retry the hotkey ~25s later. If it wedged right after resume, the GPU state-save failed — see "Suspend / resume". An unreapable wedged process needs a reboot; until then CUDA init on that GPU also hangs, so a service restart is pointless |
| "ydotool failed" | `systemctl --user status ydotoold`; is your user in the `input` group? (`id -nG`) |
| Nothing pastes, text is on clipboard | target app has no Ctrl+V; use `Shift+Super+Z` |
| CUDA out of memory | another process is on the pinned GPU: `nvidia-smi` |
| Wrong language picked | set `language = "zh"` or `"en"` if you stop code-switching |
| Recording is silent | wrong mic: check `source` against `wpctl status`, and `pactl get-source-mute <name>` |

## Uninstall

    systemctl --user disable --now voicetype ydotoold
    rm -f ~/.local/bin/voicetype-{daemon,toggle,record-fixture}
    rm -f ~/.config/systemd/user/{voicetype,ydotoold}.service
    rm -rf ~/.local/share/voicetype ~/.config/voicetype
    sudo systemctl disable --now voicetype-{pre-sleep,post-resume}
    sudo rm -f /etc/systemd/system/voicetype-{pre-sleep,post-resume}.service /etc/default/voicetype-sleep /usr/libexec/voicetype/voicetype-sleep /usr/lib/voicetype/voicetype-sleep
    sudo rm -f /etc/udev/rules.d/60-uinput-ydotool.rules

Clear the shortcuts in Settings → Keyboard → Custom Shortcuts.

### Note on cudaSetDevice

The daemon pins its GPU with `CUDA_VISIBLE_DEVICES`, not CTranslate2's
`device_index=`. `cudaSetDevice` is per-thread state, so a request arriving on
a fresh handler thread reverts to device 0 and allocates its workspace on the
wrong card. Hiding the other GPUs is the only reliable fix. Do not "simplify"
this back to `device_index=`.
