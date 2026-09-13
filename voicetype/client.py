"""Hotkey client: press once to record, press again to transcribe and paste."""

import argparse
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import time
import wave

from . import config
from .keys import to_ydotool

PID_FILE = config.STATE_DIR / "recording.pid"
WAV_FILE = config.STATE_DIR / "recording.wav"
META_FILE = config.STATE_DIR / "recording.json"
NOTIFY_ID = config.STATE_DIR / "notify.id"


# ---------------------------------------------------------------- feedback

def notify(body: str, title: str = "Voice typing", icon: str = "audio-input-microphone") -> None:
    """Desktop notification that replaces the previous one instead of stacking."""
    prev = NOTIFY_ID.read_text().strip() if NOTIFY_ID.exists() else "0"
    try:
        out = subprocess.run(
            ["notify-send", "--print-id", "--replace-id", prev or "0",
             "--app-name=voicetype", "--icon", icon, title, body],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if out.isdigit():
            NOTIFY_ID.write_text(out)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _tone(path, freq, ms=90):
    """Write a short sine blip. Avoids depending on a sound theme being present."""
    rate, n = 48000, int(48000 * ms / 1000)
    import math
    frames = bytearray()
    for i in range(n):
        # Fade the envelope in and out so the blip does not click.
        env = min(1.0, i / 240, (n - i) / 240)
        frames += struct.pack("<h", int(9000 * env * math.sin(2 * math.pi * freq * i / rate)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(bytes(frames))


def beep(kind: str) -> None:
    freq = {"start": 880, "stop": 620, "error": 300}[kind]
    path = config.STATE_DIR / f"tone-{kind}.wav"
    if not path.exists():
        _tone(path, freq)
    subprocess.Popen(["pw-play", str(path)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------- recording

def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def recording_state() -> tuple[str, int | None]:
    """("live", pid) while capturing, ("ended", None) if the cap stopped it,
    ("idle", None) otherwise.

    "ended" matters: max_seconds fires via `timeout`, and the audio captured up
    to that point should still be transcribed rather than thrown away.
    """
    if not PID_FILE.exists():
        return "idle", None
    try:
        pid = int(PID_FILE.read_text().strip())
    except ValueError:
        PID_FILE.unlink(missing_ok=True)
        return "idle", None
    if _alive(pid):
        return "live", pid
    PID_FILE.unlink(missing_ok=True)
    return "ended", None


def _current_recording():
    state, pid = recording_state()
    return pid


def start(cfg, args) -> int:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    WAV_FILE.unlink(missing_ok=True)
    proc = subprocess.Popen(
        ["timeout", "-s", "INT", str(int(cfg["max_seconds"])),
         "pw-record", "--rate", "16000", "--channels", "1", "--format", "s16",
         str(WAV_FILE)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    PID_FILE.write_text(str(proc.pid))
    META_FILE.write_text(json.dumps({
        "started": time.time(),
        "paste_key": args.paste_key or cfg["paste_key"],
        "halfwidth": args.halfwidth if args.halfwidth is not None
                     else cfg["halfwidth_punctuation"],
    }))
    if cfg["beep"]:
        beep("start")
    notify("Recording… press the hotkey again to insert text")
    return 0


def _read_meta(cfg) -> dict:
    meta = {"paste_key": cfg["paste_key"], "halfwidth": cfg["halfwidth_punctuation"],
            "started": time.time()}
    if META_FILE.exists():
        try:
            meta.update(json.loads(META_FILE.read_text()))
        except json.JSONDecodeError:
            pass
    return meta


def stop(cfg, args) -> int:
    _state, pid = recording_state()
    meta = _read_meta(cfg)
    if pid is not None:
        # SIGINT lets pw-record finalise the RIFF header; SIGKILL would not.
        try:
            os.kill(pid, signal.SIGINT)
        except ProcessLookupError:
            pass
        for _ in range(50):
            if not _alive(pid):
                break
            time.sleep(0.02)
    PID_FILE.unlink(missing_ok=True)

    if not WAV_FILE.exists() or WAV_FILE.stat().st_size < 4096:
        if cfg["beep"]:
            beep("error")
        notify("No audio captured", icon="dialog-warning")
        return 1

    notify("Transcribing…", icon="system-run")
    try:
        resp = request({"wav": str(WAV_FILE), "halfwidth": meta["halfwidth"]})
    except OSError as exc:
        if cfg["beep"]:
            beep("error")
        notify(f"Daemon unreachable: {exc}.\nTry: systemctl --user restart voicetype",
               icon="dialog-error")
        return 1

    if "error" in resp:
        if cfg["beep"]:
            beep("error")
        notify(f"Transcription failed: {resp['error']}", icon="dialog-error")
        return 1

    text = resp.get("text", "")
    if not text:
        if cfg["beep"]:
            beep("error")
        notify("No speech detected", icon="dialog-warning")
        return 0

    if cfg["beep"]:
        beep("stop")
    try:
        paste(text, meta["paste_key"])
    except RuntimeError as exc:
        notify(f"{exc}\nText is on the clipboard — paste it manually.",
               icon="dialog-error")
        return 1
    preview = text if len(text) <= 120 else text[:117] + "…"
    notify(preview, title=f"Inserted ({resp.get('language', '?')})",
           icon="insert-text")
    return 0


# ---------------------------------------------------------------- transport

def request(payload: dict, timeout: float = 120.0) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(config.SOCKET_PATH))
        s.sendall((json.dumps(payload) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.decode() or "{}")


# ---------------------------------------------------------------- insertion

def _clipboard_get() -> str | None:
    """Current clipboard text, or None if it is empty or not text."""
    try:
        r = subprocess.run(["wl-paste", "--no-newline", "--type", "text/plain"],
                           capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None


def _clipboard_set(text: str) -> None:
    subprocess.run(["wl-copy", "--"], input=text.encode(), timeout=5, check=True)


def paste(text: str, combo: str) -> None:
    """Put text on the clipboard and press the paste shortcut.

    Synthesising the characters directly would need live keymap remapping for
    CJK, which is unreliable; the clipboard carries any codepoint safely.
    """
    saved = _clipboard_get()
    _clipboard_set(text)
    # wl-copy forks to serve the selection; give the compositor a moment to
    # register the new owner before the paste keystroke asks for it.
    time.sleep(0.12)
    env = dict(os.environ)
    # ydotool talks to ydotoold over this socket; the user-level daemon puts it
    # in XDG_RUNTIME_DIR, which is not ydotool's compiled-in default.
    sock = config.STATE_DIR.parent / ".ydotool_socket"
    if sock.exists():
        env.setdefault("YDOTOOL_SOCKET", str(sock))
    try:
        subprocess.run(["ydotool", "key", *to_ydotool(combo)],
                       check=True, capture_output=True, timeout=10, env=env)
    except FileNotFoundError:
        raise RuntimeError("ydotool is not installed.") from None
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"ydotool failed: {err or exc.returncode}") from None

    if saved is not None and saved != text:
        time.sleep(1.2)                       # let the target app read it first
        try:
            _clipboard_set(saved)
        except subprocess.SubprocessError:
            pass


# ---------------------------------------------------------------- entrypoint

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="voicetype-toggle", description=__doc__)
    ap.add_argument("action", nargs="?", default="toggle",
                    choices=["toggle", "start", "stop", "cancel", "status"])
    ap.add_argument("--paste-key", help="e.g. ctrl+shift+v for terminals")
    ap.add_argument("--halfwidth", action="store_true", default=None,
                    help="force ASCII punctuation for this utterance")
    args = ap.parse_args(argv)
    cfg = config.load()
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)

    state, pid = recording_state()

    if args.action == "status":
        print(state)
        return 0
    if args.action == "cancel":
        WAV_FILE.unlink(missing_ok=True)
        if pid:
            os.kill(pid, signal.SIGINT)
            PID_FILE.unlink(missing_ok=True)
            notify("Cancelled", icon="process-stop")
        return 0

    if args.action == "start" or (args.action == "toggle" and state == "idle"):
        return start(cfg, args)
    return stop(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
