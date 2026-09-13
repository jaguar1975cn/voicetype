"""Configuration loading. Defaults are usable with no config file present."""

import os
import tomllib
from pathlib import Path

CONFIG_PATH = Path(
    os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
) / "voicetype" / "config.toml"

STATE_DIR = Path(
    os.environ.get("XDG_RUNTIME_DIR", "/tmp")
) / "voicetype"

SOCKET_PATH = STATE_DIR / "daemon.sock"

DEFAULTS = {
    "model": "large-v3-turbo",
    # GPU UUID or numeric index. A UUID is stable across reboots and driver
    # reorderings; an index is not.
    "gpu": "",
    "compute_type": "float16",
    # Empty means auto-detect per utterance, which is what code-switched
    # zh/en speech needs.
    "language": "",
    "initial_prompt": "",
    "halfwidth_punctuation": False,
    "max_seconds": 120,
    "paste_key": "ctrl+v",
    "beep": True,
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("rb") as fh:
            cfg.update(tomllib.load(fh))
    return cfg

MODEL_DIR = Path.home() / ".local" / "share" / "voicetype" / "models"
