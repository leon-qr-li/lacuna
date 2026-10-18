"""How long an import still needs (首检 #5): from this run's real speed plus this machine's past imports.

The progress bar's step weights (importer.STEPS) are fixed shares, so "elapsed × (1 − p) / p" over
the whole bar is wrong whenever a step is slower or faster than its share - e.g. at 81 % with the
AI first cut a quarter done it said "about 2 minutes" while three windows were still to come.

Instead, per step:

* finished steps cost nothing;
* the current step: its own elapsed time and fraction, blended with what this step usually takes;
  the AI first cut is modelled as it runs - the first window alone (it writes the prompt cache),
  then the rest `CONCURRENCY` at a time - from how long that first window really took;
* steps still to come: seconds per minute of audio from past imports on this machine (median),
  else measured defaults (Leon's PC, 2026-10-17: ASR 268 s + 197 s for 73.5 min, ~18 min in all).
"""
from __future__ import annotations

import math
import statistics
import time
from datetime import datetime
from pathlib import Path

from .first_cut import windows
from .store import read_json

CONCURRENCY = 3                     # ClaudeFirstCut's parallel windows after the first one
DEFAULT_RATE = {                    # seconds per minute of audio
    "models": 0.0,                  # a one-off download; its own progress tells the rest
    "asr_L": 3.6, "asr_P": 3.6, "features": 0.4, "first_cut": 7.5, "episode": 0.5,
}
TRUST_RATE_AT = 0.3                 # within a step, trust its own speed fully from 30 % on


def _audio_min(job: dict) -> float:
    durs = [t.get("duration") for t in (job.get("tracks") or {}).values() if t.get("duration")]
    if not durs and (job.get("result") or {}).get("raw_duration"):
        durs = [job["result"]["raw_duration"]]
    return max(durs) / 60 if durs else 60.0


def _ts(s: str | None) -> float | None:
    try:
        return datetime.fromisoformat(s).timestamp() if s else None
    except ValueError:
        return None


def history(root: Path) -> dict[str, float]:
    """Median seconds per audio minute for each step, from finished imports under `root`."""
    from .importer import JOB_FILE, STEPS
    samples: dict[str, list[float]] = {s: [] for s, _ in STEPS}
    if not root.is_dir():
        return {}
    for f in root.glob(f"*/{JOB_FILE}"):
        try:
            job = read_json(f)
        except (OSError, ValueError):
            continue
        steps, mins = job.get("steps") or {}, _audio_min(job)
        prev = _ts(job.get("run_started"))
        for s, _ in STEPS:
            info = steps.get(s)
            if not isinstance(info, dict):
                prev = None
                continue
            secs = info.get("seconds")
            done = _ts(info.get("done"))
            if secs is None and s == "first_cut" and prev and done and 0 < done - prev < 4 * 3600:
                secs = done - prev        # older imports only kept ASR times: the gap since features
            if s == "first_cut" and info.get("engine") not in (None, "claude"):
                secs = None               # the no-AI fallback is near-instant; not a sample
            if secs is not None and secs >= 0 and mins > 0:
                samples[s].append(secs / mins)
            prev = done
    return {s: statistics.median(v) for s, v in samples.items() if v}


def _first_cut_left(job: dict, t: float, f: float, expected: float) -> float:
    n = len(windows(_audio_min(job) * 60))
    first = job.get("step_first")
    if not first or n <= 1:
        return max(expected - t, 0.0)
    per = first[0]                       # the first window, alone
    total = per * (1 + math.ceil((n - 1) / CONCURRENCY))
    return max(total - t, 0.0)


def estimate(job: dict, hist: dict[str, float] | None = None, now: float | None = None) -> int | None:
    """Seconds left for a running import, or None before there is anything to go on."""
    from .importer import STEPS
    if job.get("state") != "running":
        return None
    hist = hist or {}
    now = time.time() if now is None else now
    mins = _audio_min(job)
    done = job.get("steps") or {}
    left, before = 0.0, 0.0
    for s, w in STEPS:
        expected = hist.get(s, DEFAULT_RATE[s]) * mins
        if s in done:
            pass
        elif s == job.get("step"):
            t = max(now - (job.get("step_at") or now), 0.0)
            f = min(max((job.get("progress", 0.0) - before) / w, 0.0), 1.0)
            if s == "first_cut":
                left += _first_cut_left(job, t, f, expected)
            else:
                by_history = max(expected - t, 0.0)
                if f >= 0.03 and t >= 5:
                    by_rate = t * (1 - f) / f
                    k = min(f / TRUST_RATE_AT, 1.0)
                    left += k * by_rate + (1 - k) * by_history
                else:
                    left += by_history
        else:
            left += expected
        before += w
    return round(left)
