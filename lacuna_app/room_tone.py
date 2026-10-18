"""Room tone for single-track erases (backlog item 8).

`pick` chooses, near an erase on one host's track, the stretch of that track's own source that
sounds most like "nobody talking": no transcript word, no transient (the loudest 10 ms frame is
what is scored, so a breath or click disqualifies a window), not digital silence, and preferably
close to the edit so the noise floor matches. `resolve` turns a bare `erase` op (track, start, end)
into one carrying that tone, so the stored op is a complete render recipe.
"""
from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from lacuna_core import SourcePool, Timeline
from lacuna_core.refine import frame_db

FRAME_MS = 10.0
SEARCH_S = 30.0          # look this far either side of the erase
MIN_TONE_S, MAX_TONE_S = 0.3, 1.5
GUARD_S = 0.3            # keep clear of the erased sound itself
WORD_GUARD_S = 0.12      # and of every transcript word on this track
DIST_DB_PER_10S = 0.6    # a slightly louder window close by beats a quieter one far away


def tone_length(n_erase: int, sr: int) -> int:
    return int(min(max(n_erase / sr, MIN_TONE_S), MAX_TONE_S) * sr)


def pick(x: np.ndarray, sr: int, x0: int, start: int, end: int, length: int,
         words: list[tuple[float, float]] = ()) -> int | None:
    """Start (in the coordinates of `x0`, i.e. x[i] is sample x0 + i) of the best room-tone window of
    `length` samples in `x`, avoiding [start, end) and `words` (seconds in the same coordinates); None
    when the track offers nothing usable (e.g. all digital silence)."""
    w = max(1, int(FRAME_MS * sr / 1000))
    db = frame_db(x, sr, FRAME_MS)
    k = max(1, -(-length // w))
    if len(db) < k:
        return None
    bad = db <= -100                               # digital silence is not room tone
    for a, b in [((start - x0) / sr - GUARD_S, (end - x0) / sr + GUARD_S)] + \
            [((s * sr - x0) / sr - WORD_GUARD_S, (e * sr - x0) / sr + WORD_GUARD_S) for s, e in words]:
        fa, fb = max(int(a * 1000 / FRAME_MS), 0), min(int(np.ceil(b * 1000 / FRAME_MS)), len(db))
        if fb > fa:
            bad[fa:fb] = True
    loud = sliding_window_view(db, k).max(axis=1)
    blocked = sliding_window_view(bad, k).any(axis=1)
    centre = ((start + end) / 2 - x0) / sr
    pos = (np.arange(len(loud)) * w + length / 2) / sr
    score = np.where(blocked, np.inf, loud + DIST_DB_PER_10S * np.abs(pos - centre) / 10.0)
    i = int(np.argmin(score))
    return None if not np.isfinite(score[i]) else x0 + i * w


TONE_KEYS = ("tone_media_id", "tone_src_in", "tone_src_out")


def misplaced(op: dict, base: Timeline) -> bool:
    """True for an erase whose stored tone lies outside the search window around it. Before
    v2026.10.18.3 `pick` returned an offset into the window instead of a track position, so erases
    later than SEARCH_S into a track took their "room tone" from the track's first minute - often
    words, looped over the erase (Leon 2026-10-18, 验收 V5). Such ops are picked again."""
    if op.get("op") != "erase" or not op.get("tone_media_id"):
        return False
    clip = next((c for c in base.track(op["track"]).clips if c.start <= op["start"] < c.end), None)
    if clip is None or clip.media_id != op["tone_media_id"]:
        return False
    margin = int((SEARCH_S + MAX_TONE_S) * base.sample_rate)
    a, b = (clip.src_in + (op[k] - clip.start) for k in ("start", "end"))
    return op["tone_src_in"] < a - margin or op["tone_src_out"] > b + margin


def resolve(op: dict, base: Timeline, pool: SourcePool, words: list[tuple[float, float]] = ()) -> dict:
    """An `erase` op with its room tone filled in (unchanged if it already has one or none is found).
    `words` are this track's transcript words in base seconds."""
    if op.get("op") != "erase" or op.get("tone_media_id"):
        return op
    sr = base.sample_rate
    track = base.track(op["track"])
    start, end = op["start"], op["end"]
    clip = next((c for c in track.clips if c.start <= start < c.end), None)
    if clip is None:
        return op
    length = tone_length(end - start, sr)
    lo = max(clip.start, start - int(SEARCH_S * sr))
    hi = min(clip.end, end + int(SEARCH_S * sr))
    x = pool.read(clip.media_id, clip.src_in + (lo - clip.start), clip.src_in + (hi - clip.start))
    at = pick(np.asarray(x, dtype=np.float64), sr, lo, start, end, length, words)
    if at is None:
        return op
    src = clip.src_in + (at - clip.start)
    return {**op, "tone_media_id": clip.media_id, "tone_src_in": int(src), "tone_src_out": int(src + length)}
