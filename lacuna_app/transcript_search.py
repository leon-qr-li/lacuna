"""逐字稿搜索 in 整集试听 (docs/decisions/2026-10-31-transcript-search.md): every place a text is said in the
current version, cut words included (tagged), matched ignoring case, width, spaces and punctuation."""
from __future__ import annotations

import unicodedata

from . import manual
from .episode import Episode

MAX_HITS = 500
MAX_QUERY = 60


def norm(s: str) -> str:
    """Lower case, full-width folded, only letters and digits (CJK count as letters)."""
    return "".join(c for c in unicodedata.normalize("NFKC", s).lower() if c.isalnum())


def search(ep: Episode, version: str | None, q: str) -> dict:
    """{hits: [{start, end, speaker, gone}], more}: timeline seconds of each match in time order; ``gone``
    when every word of it is cut (it still shows struck through in the transcript)."""
    key = norm(q[:MAX_QUERY])
    if not key:
        return {"hits": [], "more": False}
    lines = manual.transcript(ep, version, 0.0, ep.base.length / ep.sr + 1.0)
    hits: list[dict] = []
    for ln in lines:
        text, owner = "", []
        for i, w in enumerate(ln["words"]):
            n = norm(w[0])
            text += n
            owner += [i] * len(n)
        at = text.find(key)
        while at >= 0:
            ws = ln["words"][owner[at]:owner[at + len(key) - 1] + 1]
            hits.append({"start": ws[0][1], "end": max(w[2] for w in ws), "speaker": ln["speaker"],
                         "gone": all(w[3] for w in ws)})
            at = text.find(key, at + len(key))
    hits.sort(key=lambda h: h["start"])
    return {"hits": hits[:MAX_HITS], "more": len(hits) > MAX_HITS}
