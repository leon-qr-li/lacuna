"""Calibration-half loader for S5 v2 (learned rules).

EVERYTHING is filtered to raw time < CUT (2200 s) at load time, so nothing downstream can see the
held-out half (raw >= 2200 s). Spans that straddle the boundary are clipped to [.., CUT); tokens /
utterances / overlaps / gaps that end after CUT are dropped. Global S4 `stats` are never loaded.
"""
from __future__ import annotations

import bisect
import json
import os

import numpy as np

CUT = 2200.0
HOP = 0.01
HERE = os.path.dirname(os.path.abspath(__file__))
GT = os.path.join(HERE, "..", "s4_alignment", "out", "ep001_alignment.json")
TOK = os.path.join(HERE, "out", "ep001_tokens.json")
FEA = os.path.join(HERE, "out", "ep001_features.json")
NAMES = {"L": "Leon", "P": "Pei"}
NF = int(CUT / HOP)


def fr(t):
    return int(round(t / HOP))


def _clip(a, b):
    if a >= CUT:
        return None
    return (a, min(b, CUT))


def load():
    g = json.load(open(GT, encoding="utf-8"))
    # --- ground truth, clipped
    removed = {}
    for tag, nm in NAMES.items():
        removed[tag] = [c for c in (_clip(a, b) for a, b in g["removed_raw"][nm]) if c]
    muted = []
    for m in g["muted_track_spans"]:
        c = _clip(*m["raw"])
        if c:
            muted.append({"track": "L" if m["track"] == "Leon" else "P", "raw": c,
                          "verified": m["same_offset_heard_both_sides"],
                          "other_heard": m["other_track_heard_frac"]})
    segs = []
    for s in g["segments"]:
        if s["type"] != "raw":
            continue
        if s["leon_src"][0] >= CUT or s["pei_src"][0] >= CUT:
            continue
        segs.append({k: s[k] for k in ("final_start", "final_end", "leon_src", "pei_src",
                                       "offset_leon", "offset_pei")})
    del g
    # --- tokens / features, filtered
    t = json.load(open(TOK, encoding="utf-8"))["tracks"]
    toks = {k: [x for x in v if x["end"] <= CUT] for k, v in t.items()}
    f = json.load(open(FEA, encoding="utf-8"))
    utts = {k: [u for u in v if u["end"] <= CUT] for k, v in f["utterances"].items()}
    overlaps = [o for o in f["overlaps"] if o["end"] <= CUT]
    floor_gaps = [o for o in f["floor_gaps"] if o["end"] <= CUT]
    sounds = [o for o in f["sounds"] if o["end"] <= CUT]
    del f, t
    return dict(removed=removed, muted=muted, segs=segs, toks=toks, utts=utts,
                overlaps=overlaps, floor_gaps=floor_gaps, sounds=sounds)


class Calib:
    def __init__(self):
        d = load()
        self.__dict__.update(d)
        # removal masks (removed_raw ∪ verified muted); ambiguous = unverified muted
        self.rem = {k: np.zeros(NF, bool) for k in NAMES}
        self.amb = {k: np.zeros(NF, bool) for k in NAMES}
        self.cutmask = {k: np.zeros(NF, bool) for k in NAMES}
        self.mutemask = {k: np.zeros(NF, bool) for k in NAMES}
        for k in NAMES:
            for a, b in self.removed[k]:
                self.rem[k][fr(a):fr(b)] = True
                self.cutmask[k][fr(a):fr(b)] = True
        for m in self.muted:
            a, b = m["raw"]
            (self.rem if m["verified"] else self.amb)[m["track"]][fr(a):fr(b)] = True
            if m["verified"]:
                self.mutemask[m["track"]][fr(a):fr(b)] = True
        self.speech = {k: np.zeros(NF, bool) for k in NAMES}
        for k in NAMES:
            for x in self.toks[k]:
                self.speech[k][fr(x["start"]):fr(x["end"])] = True
        self._src = {k: sorted(((s["leon_src"] if k == "L" else s["pei_src"])[0],
                                (s["leon_src"] if k == "L" else s["pei_src"])[1], s["final_start"])
                               for s in self.segs) for k in NAMES}
        self._srcstarts = {k: [x[0] for x in self._src[k]] for k in NAMES}

    def to_final(self, tag, r):
        """raw time on track -> final time, or None if removed (cut)."""
        i = bisect.bisect_right(self._srcstarts[tag], r) - 1
        if i < 0:
            return None
        a, b, f0 = self._src[tag][i]
        if a <= r < b + 1e-6:
            return f0 + (r - a)
        return None

    def removed_frac(self, tag, a, b):
        s, e = fr(a), max(fr(b), fr(a) + 1)
        return float(self.rem[tag][s:e].mean())
