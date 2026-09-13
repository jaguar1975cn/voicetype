import pytest
from voicetype.client import record_command


BASE = {"max_seconds": 120, "source": ""}


def cfg(**over):
    c = dict(BASE)
    c.update(over)
    return c


def test_records_16k_mono_s16_for_whisper():
    cmd = record_command(cfg(), "/tmp/a.wav")
    assert "pw-record" in cmd
    assert cmd[cmd.index("--rate") + 1] == "16000"
    assert cmd[cmd.index("--channels") + 1] == "1"
    assert cmd[cmd.index("--format") + 1] == "s16"
    assert cmd[-1] == "/tmp/a.wav"


def test_no_target_when_source_unset():
    assert "--target" not in record_command(cfg(source=""), "/tmp/a.wav")


def test_pins_source_when_set():
    cmd = record_command(cfg(source="alsa_input.usb-0c76_x-00.mono-fallback"),
                         "/tmp/a.wav")
    assert cmd[cmd.index("--target") + 1] == "alsa_input.usb-0c76_x-00.mono-fallback"


def test_cap_uses_sigint_so_the_wav_header_is_finalised():
    cmd = record_command(cfg(max_seconds=45), "/tmp/a.wav")
    assert cmd[:4] == ["timeout", "-s", "INT", "45"]


def test_cap_is_stringified_from_any_numeric_config_value():
    assert record_command(cfg(max_seconds=30.0), "/tmp/a.wav")[3] == "30"


def test_source_with_spaces_stays_one_argv_entry():
    """argv is passed without a shell, so a name with spaces must not split."""
    cmd = record_command(cfg(source="my mic 2"), "/tmp/a.wav")
    assert cmd[cmd.index("--target") + 1] == "my mic 2"
