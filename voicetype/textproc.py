"""Cleanup of raw Whisper output before it is pasted into an application."""

import re
import unicodedata

# Whisper emits these for silence or non-speech noise. They are transcriptions
# of training-data subtitle boilerplate, not of anything the user said.
HALLUCINATIONS = {
    "thank you",
    "thanks for watching",
    "thank you for watching",
    "you",
    "bye",
    "please subscribe",
    "字幕由amara.org社群提供",
    "字幕志愿者李宗盛",
    "请不吝点赞订阅转发打赏支持明镜与点点栏目",
    "明镜与点点栏目",
    "谢谢大家",
    "谢谢观看",
    "下次再见",
    "以上就是今天的内容",
}

# Fullwidth CJK punctuation -> ASCII. The trailing space is added separately so
# that "好，好" becomes "好, 好" rather than "好,好".
_HALFWIDTH_SPACED = {
    "，": ",", "。": ".", "？": "?", "！": "!", "：": ":", "；": ";",
}
_HALFWIDTH_BARE = {
    "、": ",", "（": "(", "）": ")", "「": '"', "」": '"',
    "《": "<", "》": ">", "…": "...", "—": "-",
}

_WS = re.compile(r"\s+")


def _to_halfwidth(text: str) -> str:
    out = []
    for ch in text:
        if ch in _HALFWIDTH_SPACED:
            out.append(_HALFWIDTH_SPACED[ch] + " ")
        elif ch in _HALFWIDTH_BARE:
            out.append(_HALFWIDTH_BARE[ch])
        else:
            out.append(ch)
    return "".join(out)


def clean(text: str, halfwidth: bool = False) -> str:
    """Normalise whitespace and, optionally, CJK punctuation.

    Whisper prefixes segments with a space and may split on newlines; neither
    belongs in text that is about to be pasted at the cursor.
    """
    if halfwidth:
        text = _to_halfwidth(text)
    return _WS.sub(" ", text).strip()


def _fingerprint(text: str) -> str:
    """Casefolded, punctuation- and space-free form used for noise matching."""
    return "".join(
        ch for ch in text.casefold()
        if not unicodedata.category(ch).startswith(("P", "Z", "C"))
    )


def is_noise(text: str) -> bool:
    """True if the transcript should be discarded rather than pasted.

    Covers silence, bare punctuation, and Whisper's known silence artefacts.
    """
    fp = _fingerprint(text)
    return not fp or fp in _NOISE_FINGERPRINTS


# Built after _fingerprint is defined; the set literals above are written for
# readability, so both sides of the comparison must be normalised the same way.
_NOISE_FINGERPRINTS = frozenset(_fingerprint(h) for h in HALLUCINATIONS)
