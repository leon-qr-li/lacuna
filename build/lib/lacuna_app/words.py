"""Joining transcript words for display: Chinese characters run together, English words get spaces.

Token text is one CJK character or one Latin word (English ASR keeps punctuation on the word:
"experience,"). Two neighbours get a space between them only where both sides of the seam are
Latin, so a Chinese episode reads as before ("我看了Netflix的") and an English one reads as
English instead of "sofirstof". The same works for longer pieces (utterance texts). The web review
page applies the same rule (web/src/words.ts).
"""
from __future__ import annotations

from typing import Iterable

_NO_SPACE_BEFORE = set(",.;:!?)]}%'\"")


def _latin(c: str) -> bool:
    return "!" <= c <= "~"


def needs_space(prev: str, nxt: str) -> bool:
    return bool(prev and nxt) and _latin(prev[-1]) and _latin(nxt[0]) and nxt[0] not in _NO_SPACE_BEFORE


def is_latin(s: str) -> bool:
    """A Latin word (may carry ASCII punctuation), not a CJK character or a lone punctuation mark."""
    return bool(s) and all(_latin(c) for c in s) and any(c.isalnum() for c in s)


def join_words(words: Iterable[str]) -> str:
    out: list[str] = []
    for w in words:
        if not w:
            continue
        if out and needs_space(out[-1], w):
            out.append(" ")
        out.append(w)
    return "".join(out)
