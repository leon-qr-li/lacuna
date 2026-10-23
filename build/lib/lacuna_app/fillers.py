"""English um / uh: find them all and take them out in one step (decision `english-fillers`).

English recognisers leave most um / uh out of the text; the importer listens again to short sounds
without words (``features.build`` ``hear``) and the ones heard as um / uh / er are written into the
episode's transcript as words (``merge``), so they show in 文字稿剪辑, the chat sees them and a cut one
shows struck through like any other word. Together with the fillers the recogniser did write ("Um,"),
they are what 去掉 um / uh lists and cuts.

* ``merge(transcript, sounds, names)`` - the importer: detected fillers into the transcript words.
* ``backfill(ep)``                     - an English episode imported before the merge: once, from its import.
* ``listing(ep)``                      - every filler, whether it is still heard and where (timeline seconds).
* ``cut(ep, tracks)``                  - take out every filler still heard (of those hosts) as one undoable
  step; each is its own edit (source ``manual``, category ``filler``), so a click on one struck "uh"
  brings back only that one.

A filler is cut from every track and the timeline closes up, unless another host is talking (or making
any sound) right there: then only that host's filler is silenced, filled with their room tone.
"""
from __future__ import annotations

import bisect
import re

import numpy as np

from .episode import APPLIED, ONE_TRACK, ConflictError, Episode, subtract, to_base, to_tl
from .features import is_filler
from .i18n import tr
from .manual import _snap
from .store import read_json

CATEGORY = "filler"
PAD_S = 0.02            # a detected filler's edges come from 10 ms energy frames: a little either side ...
WORD_GAP_S = 0.01       # ... but never into the host's next or previous word
BUSY_DB = -38.0         # another track louder than this (RMS, dBFS) under the filler: silence only this host
MIN_S = 0.06


def _word(text: str) -> str:
    """What the recogniser heard, as a transcript word: "Uh." -> "uh"."""
    return " ".join(re.sub(r"[^a-z]", "", w.lower()) for w in text.split()).strip()


def merge(transcript: dict, sounds: list[dict], names: dict[str, str]) -> dict:
    """The transcript with every detected filler (``features`` sounds with ``filler``) as a word of its
    host's track, in time order. `names`: track tag -> host name. Marks the transcript as merged."""
    tracks = {k: list(v) for k, v in transcript.get("tracks", {}).items()}
    n = 0
    for s in sounds:
        name = names.get(s.get("track"))
        if not s.get("filler") or name not in tracks:
            continue
        tracks[name].append([round(float(s["start"]), 3), round(float(s["end"]), 3), _word(s.get("heard", "")) or "uh"])
        n += 1
    for words in tracks.values():
        words.sort(key=lambda w: w[0])
    return {**transcript, "tracks": tracks, "detected_fillers": n}


def backfill(ep: Episode) -> bool:
    """An English episode imported before the detected fillers went into the transcript: merge them once
    from its import's features (``<workspace>/imports/<id>``). True when the transcript changed."""
    t = ep.transcript
    if not t or "detected_fillers" in t or ep.meta.get("language") != "en":
        return False
    job_dir = ep.dir.parent.parent / "imports" / ep.dir.name
    try:
        sounds = read_json(job_dir / "features.json").get("sounds", [])
        hosts = read_json(job_dir / "job.json").get("hosts") or []
    except (OSError, ValueError):
        return False
    with ep.lock:
        ep.set_transcript(merge(t, sounds, {tag: name for tag, name in hosts}))
    return True


def _removed(ep: Episode, en: frozenset[str]):
    ripple: list[tuple[int, int, str]] = []
    lost: dict[str, list[tuple[int, int, str]]] = {}
    for i in en:
        for o in ep.edits[i].ops:
            if o["op"] == "cut":
                ripple.append((o["start"], o["end"], i))
            elif o["op"] in ONE_TRACK:
                lost.setdefault(o["track"], []).append((o["start"], o["end"], i))

    def gone(track: str, mid: int) -> str | None:
        return next((i for x, y, i in ripple if x <= mid < y), None) or \
            next((i for x, y, i in lost.get(track, ()) if x <= mid < y), None)
    return gone


def _all(ep: Episode) -> list[tuple[str, float, float, str]]:
    if ep.meta.get("language") != "en" or not ep.transcript:
        return []
    return [w for w in ep.words(0.0, float("inf")) if is_filler(w[3])]


def listing(ep: Episode) -> dict:
    """Every um / uh of an English episode (none for other languages): ``items`` [{track, text, t (timeline
    s), len, gone (edit id or None)}], per host how many are still heard / already cut, and the totals."""
    with ep.lock:
        en = ep.enabled
        cuts = ep.cuts_for(en)
        gone = _removed(ep, en)
        sr = ep.sr
        items, hosts = [], {}
        for track, s, e, w in _all(ep):
            g = gone(track, int((s + e) / 2 * sr))
            items.append({"track": track, "text": w, "t": round(to_tl(int(s * sr), cuts) / sr, 3),
                          "len": round(e - s, 3), "gone": g})
            h = hosts.setdefault(track, {"name": track, "left": 0, "cut": 0})
            h["cut" if g else "left"] += 1
        order = [t.name for t in ep.timeline_for(en).tracks]
        return {"language": ep.meta.get("language") or "zh", "items": items,
                "hosts": sorted(hosts.values(), key=lambda h: order.index(h["name"]) if h["name"] in order else 99),
                "left": sum(h["left"] for h in hosts.values()), "cut": sum(h["cut"] for h in hosts.values())}


def _busy(ep: Episode, tl, track: str, a: int, b: int) -> bool:
    """Does any other track sound (words or audio) between timeline samples a and b?"""
    ep.previewer                                  # opens the source pool
    for i, trk in enumerate(tl.tracks):
        if trk.name == track or b <= a:
            continue
        y = ep.previewer.renderer.render_track(tl, i, a, b)
        if len(y) and 10 * np.log10(float(np.mean(y ** 2)) + 1e-12) > BUSY_DB:
            return True
    return False


def cut(ep: Episode, tracks: list[str] | None = None) -> list[str]:
    """Cut every um / uh still heard (only those hosts' when `tracks` is given) as ONE undoable step.
    Returns the new edits' ids (empty when there was nothing left to cut)."""
    with ep.lock:
        en = ep.enabled
        tl = ep.timeline_for(en)
        cuts = ep.cuts_for(en)
        gone = _removed(ep, en)
        sr = ep.sr
        names = {t.name for t in tl.tracks}
        if tracks is not None and not set(tracks) <= names:
            raise ConflictError(f"unknown track in {tracks}")
        per_track: dict[str, list[tuple[float, float]]] = {}
        for trk, s, e, _ in ep.words(0.0, float("inf")):
            per_track.setdefault(trk, []).append((s, e))
        new = []
        for track, s, e, w in _all(ep):
            if (tracks is not None and track not in tracks) or track not in names:
                continue
            if gone(track, int((s + e) / 2 * sr)):
                continue
            ws = per_track.get(track, [])
            k = bisect.bisect_left(ws, (s, e))
            lo = max(s - PAD_S, ws[k - 1][1] + WORD_GAP_S if k > 0 else 0.0)
            hi = min(e + PAD_S, ws[k + 1][0] - WORD_GAP_S if k + 1 < len(ws) else e + PAD_S)
            a, b = to_tl(int(max(lo, 0.0) * sr), cuts), to_tl(int(hi * sr), cuts)
            if b - a < int(MIN_S * sr / 2):
                continue
            one = _busy(ep, tl, track, a, b)
            snap_track = track if one else None
            a2, b2 = _snap(ep, en, a, snap_track, tl.length), _snap(ep, en, b, snap_track, tl.length)
            if b2 - a2 >= int(MIN_S * sr / 2):
                a, b = a2, b2
            pieces = subtract(to_base(a, cuts, right=True), to_base(b, cuts, right=False), cuts)
            if one:
                lost = sorted((o["start"], o["end"]) for i in en for o in ep.edits[i].ops
                              if o["op"] in ONE_TRACK and o["track"] == track)
                ops = [{"op": "erase", "track": track, "start": p, "end": q}
                       for x, y in pieces for p, q in subtract(x, y, lost) if q - p >= int(0.03 * sr)]
            else:
                ops = [{"op": "cut", "start": x, "end": y, "tracks": None} for x, y in pieces if y > x]
            if not ops:
                continue
            new.append((ops, track, w, round(e - s, 2)))
        if not new:
            return []
        ids = []
        for ops, track, w, secs in new:
            title = tr("去掉口头禅「{w}」· {track}", w=w, track=track)
            e = ep.add_edit(ops, CATEGORY, title, source="manual")
            e.speech_s = secs
            ids.append(e.id)
        try:
            # history labels stay Chinese (episode.history_label shows them in the interface language)
            ep.change(f"去掉 um / uh（{len(ids)} 处）",  # i18n-ignore
                      [c for i in ids for c in ((i, "status", APPLIED), (i, "approved", True))])
        except ConflictError:
            for i in ids:
                del ep.edits[i]
            raise
        return ids
