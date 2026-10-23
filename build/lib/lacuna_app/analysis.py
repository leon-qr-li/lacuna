"""Light acoustic analysis of the *current* timeline around a playhead, for chat commands.

Works on the rendered mono mix (what the listener hears), so pauses that earlier edits already
tightened are measured as they are now, not as they were in the raw recording.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lacuna_core import frame_db

FRAME_MS = 20.0


@dataclass(frozen=True)
class Span:
    start: float   # timeline seconds
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start


def quiet_runs(x: np.ndarray, sr: int, offset_s: float, min_s: float = 0.25) -> list[Span]:
    """Runs where the mix is near its noise floor (both hosts silent)."""
    db = frame_db(x, sr, FRAME_MS)
    if len(db) == 0:
        return []
    floor = float(np.percentile(db, 10))
    loud = float(np.percentile(db, 90))
    thr = min(floor + 15.0, loud - 10.0) if loud - floor > 12 else floor + 3.0
    quiet = db < thr
    step = FRAME_MS / 1000
    runs, start = [], None
    for i, q in enumerate(np.append(quiet, False)):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) * step >= min_s:
                runs.append(Span(round(offset_s + start * step, 3), round(offset_s + i * step, 3)))
            start = None
    return runs


def speech_around(runs: list[Span], t: float, lo: float, hi: float) -> Span | None:
    """The stretch of speech between two quiet runs that contains (or follows) `t`."""
    edges = [lo] + [x for r in runs for x in (r.start, r.end)] + [hi]
    # speech intervals are (prev quiet end, next quiet start)
    speech = [Span(edges[i], edges[i + 1]) for i in range(0, len(edges) - 1, 2)
              if edges[i + 1] - edges[i] > 0.15]
    for s in speech:
        if s.start <= t < s.end:
            return s
    later = [s for s in speech if s.start >= t]
    return later[0] if later else (speech[-1] if speech else None)
