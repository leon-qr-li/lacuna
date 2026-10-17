"""Which first-cut edits need Leon's judgement, and in what order he sees them."""
from __future__ import annotations

REVIEW_CONFIDENCE = 0.4   # below this the AI is unsure enough that Leon should listen.
# The S5 editor reports 0.5-0.6 for most routine cuts (v3: 434 of 646 edits under 0.6), so 0.6
# flooded the queue; pauses are never queued on confidence alone.
REVIEW_SPEECH_S = 1.5     # removing more speech than this is never routine


def needs_review(category: str, confidence: float, speech_s: float) -> bool:
    """Content trims, moved interjections, low confidence or a lot of speech removed. `category` is the app category
    (content / filler / pause ...). Everything else is routine: auto-applied, grouped by
    category, restorable."""
    if category in ("content", "interjection") or speech_s > REVIEW_SPEECH_S:
        return True
    return category != "pause" and confidence < REVIEW_CONFIDENCE


def review_sort_key(d: dict) -> tuple:
    """For edit_json dicts: content trims first, then by duration removed (longest first),
    then timeline order."""
    return (d["category"] != "content", -d["len"], d["t"])
