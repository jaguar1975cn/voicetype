"""Resident Whisper model behind a unix socket.

Loading large-v3-turbo takes 10-20s, which would be paid on every dictation if
the model lived in the hotkey client. The daemon pays it once at login.
"""

import json
import logging
import os
import socket
import socketserver
import sys
import threading
import time

from . import config
from .cudalibs import preload
from .textproc import clean, is_noise

log = logging.getLogger("voicetype")

_model = None
_model_lock = threading.Lock()
_gpu_lock = threading.Lock()

# A native (CUDA) hang inside model.transcribe cannot be unwound from Python:
# py-spy and gdb both failed to catch the wedged thread at a safe point, and
# every later request then queues behind _gpu_lock forever -- the hotkey
# "records" but no response ever returns. The only recovery is to exit
# nonzero and let systemd's Restart=on-failure bring the daemon back.
# Measured transcribes run ~1s; 60s leaves headroom for a full max_seconds
# clip on the slowest pinned GPU.
TRANSCRIBE_TIMEOUT = 60.0

# monotonic timestamp of the in-flight request, or None when idle. A single
# float written/cleared under the GIL is safe enough for a 2s poll.
_busy_since: float | None = None


def pin_gpu(gpu: str) -> None:
    """Restrict the process to one GPU, before any CUDA initialisation.

    device_index= is not enough: cudaSetDevice is per-thread state, so a
    request handler running in a fresh thread reverts to device 0 and
    allocates its workspace on the wrong card. Hiding every other device
    makes that impossible. CUDA_VISIBLE_DEVICES accepts a GPU-<uuid> string,
    which -- unlike an index -- survives driver reordering.
    """
    if not gpu:
        return
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu
    log.info("pinned to %s", gpu)


def _vram() -> str:
    import subprocess
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.used,memory.total",
             "--format=csv,noheader"], capture_output=True, text=True, timeout=5).stdout
        return " [" + "; ".join(l.strip() for l in out.splitlines()) + "]"
    except Exception:
        return ""


def get_model(cfg):
    global _model
    with _model_lock:
        if _model is None:
            preload()
            from faster_whisper import WhisperModel
            t = time.time()
            _model = WhisperModel(
                cfg["model"],
                device="cuda",
                device_index=0,
                compute_type=cfg["compute_type"],
                download_root=str(config.MODEL_DIR),
            )
            log.info("model %s loaded in %.1fs%s",
                     cfg["model"], time.time() - t, _vram())
    return _model


def transcribe(wav_path: str, cfg: dict) -> dict:
    global _busy_since
    _busy_since = time.monotonic()
    try:
        model = get_model(cfg)
        t = time.time()
        with _gpu_lock:
            segments, info = model.transcribe(
                wav_path,
                language=cfg["language"] or None,
                initial_prompt=cfg["initial_prompt"] or None,
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            # Generation is lazy; the GPU work happens while draining segments.
            raw = "".join(s.text for s in segments)
        text = clean(raw, halfwidth=cfg["halfwidth_punctuation"])
        if is_noise(text):
            text = ""
        log.info(
            "transcribed %.1fs audio in %.2fs lang=%s -> %d chars",
            info.duration, time.time() - t, info.language, len(text),
        )
        return {"text": text, "language": info.language,
                "audio_seconds": info.duration}
    finally:
        _busy_since = None


def _stuck(deadline: float) -> bool:
    started = _busy_since
    return started is not None and time.monotonic() - started > deadline


def _watchdog(deadline: float = TRANSCRIBE_TIMEOUT) -> None:
    while True:
        time.sleep(2.0)
        if _stuck(deadline):
            log.error("transcription wedged >%.0fs; exiting for systemd "
                      "restart", deadline)
            os._exit(42)


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline()
        if not line:
            return
        try:
            req = json.loads(line)
            cfg = config.load()
            if req.get("halfwidth") is not None:
                cfg["halfwidth_punctuation"] = req["halfwidth"]
            resp = transcribe(req["wav"], cfg)
        except Exception as exc:                      # keep the daemon alive
            log.exception("request failed")
            resp = {"error": f"{type(exc).__name__}: {exc}"}
        self.wfile.write((json.dumps(resp) + "\n").encode())


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    cfg = config.load()
    pin_gpu(cfg["gpu"])
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    if config.SOCKET_PATH.exists():
        config.SOCKET_PATH.unlink()

    # Load before accepting connections so the first hotkey press is not the
    # one that waits 20s for the model.
    get_model(cfg)
    threading.Thread(target=_watchdog, daemon=True).start()

    with Server(str(config.SOCKET_PATH), Handler) as srv:
        os.chmod(config.SOCKET_PATH, 0o600)
        log.info("listening on %s", config.SOCKET_PATH)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            config.SOCKET_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
