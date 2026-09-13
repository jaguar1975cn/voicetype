"""Record a test fixture through the same path dictation uses.

Shelling out to a bare pw-record here would capture from the system default
source, not the mic pinned in the config, so fixtures would not test the
device actually being dictated into.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from . import config
from .client import record_command

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="voicetype-record-fixture")
    ap.add_argument("name", help="fixture name, without .wav")
    ap.add_argument("seconds", nargs="?", type=int, default=6)
    args = ap.parse_args(argv)

    cfg = config.load()
    cfg["max_seconds"] = args.seconds          # the cap is the recording length
    dest = FIXTURE_DIR / f"{args.name}.wav"
    dest.parent.mkdir(parents=True, exist_ok=True)

    src = cfg.get("source") or "(system default)"
    print(f"Recording {args.seconds}s from {src}\n  -> {dest}\nSpeak now.")
    subprocess.run(record_command(cfg, dest))
    if dest.exists():
        print(f"Saved {dest.stat().st_size // 1024} KiB")
        return 0
    print("Nothing recorded.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
