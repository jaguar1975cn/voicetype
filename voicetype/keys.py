"""Translate key names like "ctrl+shift+v" into ydotool's keycode syntax.

ydotool 1.0 dropped key *names* in favour of raw Linux evdev keycodes with
:1 for press and :0 for release, so "ctrl+v" must become "29:1 47:1 47:0 29:0".
"""

# From linux/input-event-codes.h. Only what a paste shortcut needs.
KEYCODES = {
    "ctrl": 29, "leftctrl": 29, "rightctrl": 97,
    "shift": 42, "leftshift": 42, "rightshift": 54,
    "alt": 56, "leftalt": 56, "rightalt": 100,
    "super": 125, "meta": 125,
    "v": 47, "c": 46, "x": 45, "a": 30,
    "insert": 110, "enter": 28, "space": 57,
}


def to_ydotool(combo: str) -> list[str]:
    """"ctrl+shift+v" -> ["29:1", "42:1", "47:1", "47:0", "42:0", "29:0"]

    Modifiers are released in reverse order so the sequence is balanced.
    """
    names = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not names:
        raise ValueError("empty key combination")
    try:
        codes = [KEYCODES[n] for n in names]
    except KeyError as exc:
        raise ValueError(f"unknown key name: {exc.args[0]}") from None
    presses = [f"{c}:1" for c in codes]
    releases = [f"{c}:0" for c in reversed(codes)]
    return presses + releases
