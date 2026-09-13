import pytest
from voicetype.keys import to_ydotool


def test_ctrl_v():
    assert to_ydotool("ctrl+v") == ["29:1", "47:1", "47:0", "29:0"]


def test_ctrl_shift_v_releases_in_reverse():
    assert to_ydotool("ctrl+shift+v") == [
        "29:1", "42:1", "47:1", "47:0", "42:0", "29:0",
    ]


def test_is_case_and_space_insensitive():
    assert to_ydotool(" Ctrl + V ") == to_ydotool("ctrl+v")


def test_single_key():
    assert to_ydotool("enter") == ["28:1", "28:0"]


def test_press_and_release_counts_are_balanced():
    seq = to_ydotool("ctrl+shift+v")
    assert sum(s.endswith(":1") for s in seq) == sum(s.endswith(":0") for s in seq)


def test_unknown_key_rejected():
    with pytest.raises(ValueError, match="unknown key name: f13"):
        to_ydotool("ctrl+f13")


def test_empty_rejected():
    with pytest.raises(ValueError, match="empty key combination"):
        to_ydotool("  ")
