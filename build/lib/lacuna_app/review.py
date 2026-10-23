"""Which first-cut edits need Leon's judgement, and in what order he sees them."""
from __future__ import annotations

from dataclasses import dataclass, field

REVIEW_CONFIDENCE = 0.4   # below this the AI is unsure enough that Leon should listen.
# The S5 editor reports 0.5-0.6 for most routine cuts (v3: 434 of 646 edits under 0.6), so 0.6
# flooded the queue; pauses are never queued on confidence alone.
REVIEW_SPEECH_S = 1.5     # removing more speech than this is never routine
TRUSTED_SPEECH_S = 5.0    # a kind Leon trusts still goes to review above this much speech


@dataclass
class ReviewPolicy:
    """Calibration learned from Leon's reviews and approved by him (`lacuna_app.learning`).
    `by_kind[(kind, host)]` forces review on (True) or off (False) for that AI category on that host's
    speech; `confidence` replaces REVIEW_CONFIDENCE."""
    by_kind: dict[tuple[str, str], bool] = field(default_factory=dict)
    confidence: float = REVIEW_CONFIDENCE


def needs_review(category: str, confidence: float, speech_s: float, *, kind: str | None = None,
                 host: str | None = None, policy: ReviewPolicy | None = None) -> bool:
    """Content trims, moved interjections, low confidence or a lot of speech removed. `category` is the app category
    (content / filler / pause ...), `kind` the AI's finer category, `host` whose speech the edit removes.
    Everything else is routine: auto-applied, grouped by category, restorable."""
    threshold = REVIEW_CONFIDENCE
    if policy is not None:
        threshold = policy.confidence
        forced = policy.by_kind.get((kind or category, host or ""))
        if forced is True:
            return True
        if forced is False:
            return speech_s > TRUSTED_SPEECH_S
    if category in ("content", "interjection") or speech_s > REVIEW_SPEECH_S:
        return True
    return category != "pause" and confidence < threshold


def review_sort_key(d: dict) -> tuple:
    """For edit_json dicts: timeline order, from the first second (Leon listens through the episode;
    the old content-first / longest-first order jumped around)."""
    return (d["t"], d["id"])
