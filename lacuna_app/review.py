"""Which first-cut edits need Leon's judgement, and in what order he sees them."""
from __future__ import annotations

REVIEW_CONFIDENCE = 0.6   # below this the AI is unsure enough that Leon should listen
REVIEW_SPEECH_S = 1.5     # removing more speech than this is never routine


def needs_review(category: str, confidence: float, speech_s: float) -> bool:
    """Content trims, low confidence or a lot of speech removed. `category` is the app category
    (content / filler / pause ...). Everything else is routine: auto-applied, grouped by
    category, restorable."""
    return category == "content" or confidence < REVIEW_CONFIDENCE or speech_s > REVIEW_SPEECH_S


def review_sort_key(d: dict) -> tuple:
    """For edit_json dicts: content trims first, then by duration removed (longest first),
    then timeline order."""
    return (d["category"] != "content", -d["len"], d["t"])
