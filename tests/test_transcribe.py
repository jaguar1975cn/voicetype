"""End-to-end tests. These need the GPU and the model, so they are slow."""

import socket
from pathlib import Path

import pytest

from voicetype import config

FIXTURES = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.slow


def _daemon_up() -> bool:
    if not config.SOCKET_PATH.exists():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect(str(config.SOCKET_PATH))
        return True
    except OSError:
        return False


needs_daemon = pytest.mark.skipif(
    not _daemon_up(), reason="daemon not running: systemctl --user start voicetype"
)


def transcribe(name: str) -> dict:
    from voicetype.client import request
    path = FIXTURES / name
    if not path.exists():
        pytest.skip(f"fixture {name} not recorded; see fixtures/README.md")
    return request({"wav": str(path)})


@needs_daemon
def test_english_is_transcribed():
    r = transcribe("en_refactor.wav")
    assert "error" not in r, r
    assert "refactor" in r["text"].lower()
    assert r["language"] == "en"


@needs_daemon
def test_code_switched_zh_en():
    """One model, both languages: English terms survive as English.

    The failure this guards against is transliteration -- the decoder picking
    zh for the whole segment and rendering an English word as same-sounding
    hanzi ("function" -> "方形") -- not merely dropping the word.

    Expected recording: 这个 API 的 response 有点慢，需要加 cache
    """
    r = transcribe("mixed_zh_en.wav")
    assert "error" not in r, r
    text = r["text"]
    assert any("一" <= c <= "鿿" for c in text), f"Chinese lost: {text!r}"
    missing = [w for w in ("api", "response", "cache") if w not in text.lower()]
    assert not missing, f"English terms {missing} transliterated or dropped: {text!r}"


@needs_daemon
def test_silence_yields_empty_not_hallucination():
    import wave, struct, tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
        path = fh.name
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(struct.pack("<h", 0) * 16000 * 3)
    try:
        from voicetype.client import request
        r = request({"wav": path})
        assert r.get("text") == "", f"silence produced {r.get('text')!r}"
    finally:
        os.unlink(path)
