"""Manual editing: Leon selects a stretch of the timeline himself and cuts it (decision `manual-editing`).

A manual cut is an ordinary `Edit` (source ``manual``, category ``manual``), so everything that works on
AI edits works on it too: undo / redo, restore in the edit lists, the AI producer sees it among the nearby
edits, export renders it, and learning counts it as a cut Leon added himself (still only a *candidate*
rule until he confirms it). Nothing here touches the AI first cut, review or chat.

* ``cut(ep, start, end, track)`` - timeline seconds. ``track=None`` removes the stretch from every track
  and closes the gap (``cut``); a track name silences only that host there, filled with room tone
  (``erase``), the timeline does not move. Boundaries are nudged to the quietest nearby sample.
* ``wave(ep, version, tile)``    - per-track peak levels of one tile of a timeline version (what the
  lanes draw), rendered on demand and cached.
* ``transcript(ep, version, t0, t1)`` - the transcript of a stretch of that version, words already cut
  included and marked with the edit that removed them (shown struck through; a click restores the edit).
"""
from __future__ import annotations

from collections import OrderedDict

import numpy as np
from lacuna_core.refine import snap_cut

from .episode import APPLIED, ONE_TRACK, ConflictError, Episode, subtract, to_base, to_tl
from .i18n import tr
from .words import join_words

CATEGORY = "manual"
MIN_CUT_S = 0.05            # shorter selections are a click, not a cut
SNAP_MS = 60.0              # how far a boundary may move to land in a quiet spot
TILE_S = 10.0               # waveform tiles: seconds of timeline per request ...
PER_S = 100                 # ... and peak values per second (per track)
_WAVES: OrderedDict[tuple, dict] = OrderedDict()
_WAVES_MAX = 256


def _enabled(ep: Episode, version: str | None) -> frozenset[str]:
    if not version:
        return ep.enabled
    en = ep.enabled_for_key(version)
    if en is None:
        if version != ep.version_key():
            raise KeyError(version)
        en = ep.enabled
    return en


def wave(ep: Episode, version: str | None, tile: int) -> dict:
    """Peaks (0-100, square-root scaled so quiet speech still shows) of timeline tile `tile`."""
    with ep.lock:
        en = _enabled(ep, version)
        key = (str(ep.dir), ep.version_key(en), tile)
        hit = _WAVES.get(key)
        if hit is not None:
            _WAVES.move_to_end(key)
            return hit
        tl = ep.timeline_for(en)
        sr = ep.sr
        a = int(tile * TILE_S * sr)
        b = min(int((tile + 1) * TILE_S * sr), tl.length)
        step = sr // PER_S
        tracks = []
        ep.previewer                                  # opens the source pool
        renderer = ep.previewer.renderer
        for i, trk in enumerate(tl.tracks):
            if b <= a:
                peaks: list[int] = []
            else:
                y = np.abs(renderer.render_track(tl, i, a, b))
                n = -(-len(y) // step)
                y = np.pad(y, (0, n * step - len(y)))
                pk = np.sqrt(np.clip(y.reshape(n, step).max(axis=1), 0, 1))
                peaks = np.round(pk * 100).astype(int).tolist()
            tracks.append({"name": trk.name, "peaks": peaks})
        out = {"tile": tile, "start": round(a / sr, 3), "per_s": PER_S, "tracks": tracks}
        _WAVES[key] = out
        while len(_WAVES) > _WAVES_MAX:
            _WAVES.popitem(last=False)
        return out


def transcript(ep: Episode, version: str | None, t0: float, t1: float) -> list[dict]:
    """The transcript between timeline t0 and t1 of that version, cut words included: each line is one
    host's run of words, ``words`` = [text, start, end, edit id that removed it or None, base start]
    (timeline seconds; a removed word sits at the point it was cut from)."""
    with ep.lock:
        en = _enabled(ep, version)
        cuts = ep.cuts_for(en)
        sr = ep.sr
        if not ep.transcript:
            return []
        a_s, b_s = to_base(int(max(t0, 0.0) * sr), cuts) / sr, to_base(int(t1 * sr), cuts, right=False) / sr
        ripple: list[tuple[int, int, str]] = []
        lost: dict[str, list[tuple[int, int, str]]] = {}
        slips: dict[str, list[tuple[int, int, int]]] = {}
        for i in en:
            for o in ep.edits[i].ops:
                if o["op"] == "cut":
                    ripple.append((o["start"], o["end"], i))
                elif o["op"] in ONE_TRACK:
                    lost.setdefault(o["track"], []).append((o["start"], o["end"], i))
                elif o["op"] == "slip":
                    slips.setdefault(o["track"], []).append((o["start"], o["end"], o["delta"]))
        runs: dict[str, list[list]] = {}
        for track, s, e, w in ep.words(a_s, b_s):
            mid = int((s + e) / 2 * sr)
            gone = next((i for x, y, i in ripple if x <= mid < y), None) or \
                next((i for x, y, i in lost.get(track, ()) if x <= mid < y), None)
            d = 0 if gone else next((dl for x, y, dl in slips.get(track, ()) if x <= mid < y), 0)
            ts, te = to_tl(int(s * sr) + d, cuts) / sr, to_tl(int(e * sr) + d, cuts) / sr
            if not t0 <= ts < t1:
                continue
            word = [w, round(ts, 3), round(max(te, ts + (0 if gone else 0.01)), 3), gone, round(s, 3)]
            rs = runs.setdefault(track, [])
            if rs and s - rs[-1][-1][5] <= 0.6:
                rs[-1].append(word + [e])
            else:
                rs.append([word + [e]])
        lines = [{"speaker": track, "start": r[0][1], "words": [x[:5] for x in r]}
                 for track, rs in runs.items() for r in rs]
        return sorted(lines, key=lambda ln: (ln["start"], ln["words"][0][4]))


def _snap(ep: Episode, en: frozenset[str], t: int, track: str | None, length: int) -> int:
    r = int(SNAP_MS * ep.sr / 1000) + int(0.01 * ep.sr)
    a, b = max(t - r, 0), min(t + r, length)
    if b - a < 2 or not 0 < t < length:
        return t
    tl = ep.timeline_for(en)
    if track is None:
        sig = ep.render(en, a, b)[:, 0]
    else:
        i = next((k for k, x in enumerate(tl.tracks) if x.name == track), None)
        if i is None:
            return t
        ep.previewer
        sig = ep.previewer.renderer.render_track(tl, i, a, b)
    return a + snap_cut([sig], t - a, ep.sr, radius_ms=SNAP_MS)


def _said(ep: Episode, en: frozenset[str], cuts, a_s: float, b_s: float, track: str | None) -> tuple[str, float]:
    """The words the selection removes (as heard on this version) and how many seconds of speech."""
    text, speech = [], 0.0
    for u in ep.utterances(max(a_s - 1, 0.0), b_s + 1, en, cuts):
        if track and u.speaker != track:
            continue
        for w in u.words:
            if a_s <= (w.start + w.end) / 2 < b_s:
                text.append(w.text)
                speech += min(w.end, b_s) - max(w.start, a_s)
    return join_words(text), round(max(speech, 0.0), 2)


def cut(ep: Episode, start: float, end: float, track: str | None = None) -> str:
    """Cut timeline [start, end) (seconds) as one undoable manual edit; returns its id."""
    with ep.lock:
        en = ep.enabled
        tl = ep.timeline_for(en)
        cuts = ep.cuts_for(en)
        sr = ep.sr
        if track is not None and track not in {x.name for x in tl.tracks}:
            raise ConflictError(tr("没有这条音轨：{track}", track=track))
        a = max(int(start * sr), 0)
        b = min(int(end * sr), tl.length)
        if b - a < int(MIN_CUT_S * sr):
            raise ConflictError(tr("选中的太短了，拖动多选一点再剪"))
        a, b = _snap(ep, en, a, track, tl.length), _snap(ep, en, b, track, tl.length)
        if b - a < int(MIN_CUT_S * sr):
            raise ConflictError(tr("选中的太短了，拖动多选一点再剪"))
        pieces = subtract(to_base(a, cuts, right=True), to_base(b, cuts, right=False), cuts)
        if track is None:
            ops = [{"op": "cut", "start": x, "end": y, "tracks": None} for x, y in pieces]
        else:
            # what this host has already lost here (an earlier one-track edit) is left as it is
            gone = sorted((o["start"], o["end"]) for i in en for o in ep.edits[i].ops
                          if o["op"] in ONE_TRACK and o["track"] == track)
            ops = [{"op": "erase", "track": track, "start": p, "end": q}
                   for x, y in pieces for p, q in subtract(x, y, gone) if q - p >= int(0.03 * sr)]
        if not ops:
            raise ConflictError(tr("这一段已经剪掉了"))
        said, speech = _said(ep, en, cuts, a / sr, b / sr, track)
        secs = f"{(b - a) / sr:.1f}"
        quote = f"「{said[:24]}{'…' if len(said) > 24 else ''}」" if said else ""
        title = (tr("手动删除 {s} 秒", s=secs) if track is None else tr("{track} 单轨静音 {s} 秒", track=track, s=secs)) \
            + (f" · {quote}" if quote else "")
        e = ep.add_edit(ops, CATEGORY, title, source="manual")
        e.speech_s = speech
        try:
            # history labels stay Chinese (episode.history_label shows them in the interface language)
            ep.change(f"手动剪辑：{title}",  # i18n-ignore
                      [(e.id, "status", APPLIED), (e.id, "approved", True)])
        except ConflictError:
            del ep.edits[e.id]
            raise
        return e.id
