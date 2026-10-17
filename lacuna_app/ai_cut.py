"""Turn the AI editor's first-cut ops (spikes/s5_first_cut/edit_ops.schema.json) into app Edits.

Input ops reference the raw host tracks by token id (``L000812``) or raw seconds. Output edits
hold lacuna_core op dicts in **base** coordinates (base sample 0 = raw second ``w0``), exactly
like the demo episode, so everything downstream (review, restore, undo, render) is unchanged.

Mapping (every op only removes or moves source ranges; nothing here can create audio):

* ``cut`` track ``both``          -> ripple ``cut`` on all tracks.
* ``cut`` on one track            -> ``lift`` on that track (the other host stays continuous and
  in sync). If the other track has no words anywhere near the range (and it is not a
  noise op), the range is silence there too, so it becomes a ripple ``cut`` that actually
  shortens the episode.
* ``tighten_pause``               -> ripple ``cut`` of the excess from the middle of the pause
  (``both``: the floor gap where neither host speaks). A one-track pause while the other host
  talks would need per-track re-timing, which the episode model does not do yet: skipped and
  counted.
* ``slip``                        -> lacuna_core ``slip`` on that track (no audio removed).
* ``keep_flag`` with suggested cut -> an edit that is *not* applied (status restored) so Leon can
  apply it from the review list.

Cut points are refined with ``lacuna_core.refine.snap_cut`` on the source audio (token times
from ASR are only approximate). Overlapping results are trimmed so no two ripple cuts overlap.
"""
from __future__ import annotations

import bisect
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from lacuna_core import MediaRef, Project, SourcePool, new_timeline
from lacuna_core.edl import Clip, Track, replace
from lacuna_core.refine import snap_cut

from .episode import APPLIED, RESTORED, Edit
from .review import ReviewPolicy, needs_review
from .i18n import N_, tr

TRACK_NAMES = {"L": "Leon", "P": "Pei"}
CATEGORY_MAP = {
    "pause": "pause",
    "disfluency": "filler",
    "repetition": "filler",
    "crosstalk": "crosstalk",
    "content": "content",
    "interjection_move": "interjection",
    "single_track_noise": "single_track",
}
AI_CATEGORY_LABELS = {
    "pause": N_("停顿"), "disfluency": N_("口误"), "repetition": N_("重复"), "crosstalk": N_("抢话"),
    "content": N_("内容删减"), "interjection_move": N_("插话挪位"), "single_track_noise": N_("单轨杂声"),
}


MIN_CUT_S = 0.01          # shorter results are dropped
TOKEN_SNAP_MS = 100.0     # token edges come from ASR / line interpolation: allow some search
PAUSE_SNAP_MS = 30.0      # inside a pause only a small nudge is needed
NEAR_WORDS_S = 0.15       # "the other track is silent" margin

Reader = Callable[[str, int, int], np.ndarray]   # (track name, base start, base end) -> samples


# --------------------------------------------------------------------------- tokens

class TrackTokens:
    def __init__(self, toks: list[dict]):
        self.toks = sorted(toks, key=lambda t: t["start"])
        self.ids = {t["id"]: i for i, t in enumerate(self.toks)}
        self.starts = [t["start"] for t in self.toks]
        self.ends = [t["end"] for t in self.toks]
        # tokens are short and (almost) non-overlapping; a running max of ends keeps lookups safe
        self.max_end = list(np.maximum.accumulate(self.ends)) if self.ends else []

    def overlapping(self, a: float, b: float) -> list[dict]:
        if not self.toks:
            return []
        i0 = bisect.bisect_right(self.max_end, a)
        out = []
        for t in self.toks[i0:]:
            if t["start"] >= b:
                break
            if t["end"] > a:
                out.append(t)
        return out

    def speech_in(self, a: float, b: float) -> float:
        return sum(min(b, t["end"]) - max(a, t["start"]) for t in self.overlapping(a, b))

    def text_in(self, a: float, b: float) -> str:
        return "".join(t["t"] for t in self.overlapping(a, b)
                       if (min(b, t["end"]) - max(a, t["start"])) >= 0.5 * (t["end"] - t["start"]))

    def gap_at(self, t: float) -> tuple[float, float] | None:
        """(gap start, gap end) of the pause containing raw time t, None if t is inside a word."""
        i = bisect.bisect_right(self.starts, t) - 1
        if i >= 0 and self.max_end[i] > t:
            return None
        a = self.max_end[i] if i >= 0 else 0.0
        b = self.starts[i + 1] if i + 1 < len(self.toks) else float("inf")
        return a, b


def load_tokens(path: str | Path) -> dict[str, TrackTokens]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return {tag: TrackTokens(toks) for tag, toks in d["tracks"].items()}


# --------------------------------------------------------------------------- conversion

@dataclass
class Report:
    ops_in: int = 0
    edits_out: int = 0
    skipped: Counter = field(default_factory=Counter)      # reason -> count
    converted: Counter = field(default_factory=Counter)    # "cut->lift" etc.
    warnings: list[str] = field(default_factory=list)

    def skip(self, op_id: str, reason: str, detail: str = "") -> None:
        self.skipped[reason] += 1
        self.warnings.append(f"{op_id}: {reason}{(' (' + detail + ')') if detail else ''}")

    def summary(self) -> str:
        parts = [f"{self.ops_in} ops -> {self.edits_out} edits"]
        if self.converted:
            parts.append("converted: " + ", ".join(f"{k} {v}" for k, v in sorted(self.converted.items())))
        if self.skipped:
            parts.append("skipped: " + ", ".join(f"{k} {v}" for k, v in sorted(self.skipped.items())))
        return "; ".join(parts)


class _OpError(ValueError):
    pass


class Converter:
    def __init__(self, tokens: dict[str, TrackTokens], sr: int, w0: float = 0.0,
                 w1: float = float("inf"), read: Reader | None = None, policy: ReviewPolicy | None = None):
        self.tokens = tokens
        self.policy = policy
        self.sr = sr
        self.w0, self.w1 = w0, w1
        self.read = read
        self.report = Report()

    # ---- coordinates
    def S(self, t: float) -> int:
        """raw seconds -> base samples"""
        return int(round((t - self.w0) * self.sr))

    def point(self, p, end: bool) -> float:
        if isinstance(p, str):
            tr = self.tokens.get(p[:1])
            if tr is None or p not in tr.ids:
                raise _OpError(f"unknown token {p}")
            t = tr.toks[tr.ids[p]]
            return float(t["end"] if end else t["start"])
        if isinstance(p, (int, float)) and not isinstance(p, bool):
            return float(p)
        raise _OpError(f"bad point {p!r}")

    def in_window(self, a: float, b: float) -> bool:
        return a >= self.w0 and b <= self.w1

    # ---- refinement
    def snap(self, names: list[str], x: int, radius_ms: float, lo: int | None = None,
             hi: int | None = None) -> int:
        if self.read is None:
            y = x
        else:
            r = int(radius_ms * self.sr / 1000) + int(0.01 * self.sr) + 2
            a = max(x - r, 0)
            sigs = [self.read(n, a, x + r + 1) for n in names]
            y = a + snap_cut(sigs, x - a, self.sr, radius_ms=radius_ms)
        if lo is not None:
            y = max(y, lo)
        if hi is not None:
            y = min(y, hi)
        return y

    def snap_range(self, names: list[str], a: float, b: float, radius_ms: float,
                   bounds: tuple[float, float] | None = None) -> tuple[int, int]:
        lo = self.S(bounds[0]) if bounds else None
        hi = self.S(bounds[1]) if bounds and np.isfinite(bounds[1]) else None
        # never let the two ends cross: each end may move at most to the middle
        mid = self.S((a + b) / 2)
        sa = self.snap(names, self.S(a), radius_ms, lo, mid if hi is None else min(mid, hi))
        sb = self.snap(names, self.S(b), radius_ms, max(mid, lo) if lo is not None else mid, hi)
        return sa, sb

    # ---- helpers
    def other_silent(self, tag: str, a: float, b: float) -> bool:
        other = [t for t in self.tokens if t != tag]
        return all(not self.tokens[o].overlapping(a - NEAR_WORDS_S, b + NEAR_WORDS_S) for o in other)

    def speech(self, tags: Iterable[str], a: float, b: float) -> float:
        return sum(self.tokens[t].speech_in(a, b) for t in tags if t in self.tokens)

    def host(self, tags: list[str], a: float, b: float) -> str:
        """Whose speech [a, b) removes on `tags`: Leon / Pei / both / none (same rule as learning.decisions)."""
        per = {TRACK_NAMES[t]: self.tokens[t].speech_in(a, b) for t in tags if t in self.tokens}
        top = max(per.values(), default=0.0)
        if top < 0.05:
            return "none"
        big = [t for t, v in per.items() if v >= 0.3 * top]
        return big[0] if len(big) == 1 else "both"

    def text(self, tags: Iterable[str], a: float, b: float) -> str:
        return " / ".join(s for s in (self.tokens[t].text_in(a, b) for t in tags if t in self.tokens) if s)

    # ---- per op
    def convert_op(self, o: dict) -> Edit | None:
        kind = o.get("op")
        oid = str(o.get("id", "?"))
        ai_cat = o.get("category", "")
        cat = CATEGORY_MAP.get(ai_cat)
        if cat is None:
            raise _OpError(f"unknown category {ai_cat!r}")
        track = o.get("track")
        if track not in ("L", "P", "both"):
            raise _OpError(f"bad track {track!r}")
        conf = float(o.get("confidence", 0.5))
        reason = str(o.get("reason", "")).strip()
        all_tags = list(TRACK_NAMES)

        if kind in ("cut", "keep_flag"):
            if kind == "keep_flag" and o.get("suggested", "cut") != "cut":
                raise _OpError("keep_flag only supported for a suggested cut")
            a, b = self.point(o["from"], False), self.point(o["to"], True)
            if b - a < MIN_CUT_S:
                raise _OpError("empty or reversed range")
            if not self.in_window(a, b):
                return self._outside(oid)
            if track == "both" or (ai_cat != "single_track_noise" and self.other_silent(track, a, b)):
                tags = all_tags
                x, y = self.snap_range([TRACK_NAMES[t] for t in tags], a, b, TOKEN_SNAP_MS)
                ops = [{"op": "cut", "start": x, "end": y, "tracks": None}]
                if track != "both":
                    self.report.converted["单轨 cut→双轨 cut（对方无声）"] += 1  # i18n-ignore
            else:
                tags = [track]
                x, y = self.snap_range([TRACK_NAMES[track]], a, b, TOKEN_SNAP_MS)
                ops = [{"op": "lift", "track": TRACK_NAMES[track], "start": x, "end": y}]
                self.report.converted["单轨 cut→lift"] += 1  # i18n-ignore
            if (y - x) < MIN_CUT_S * self.sr:
                raise _OpError("range vanished after snapping")
            sp = self.speech(tags, a, b)
            dur = (y - x) / self.sr
            title = self._title(ai_cat, cat, tags, dur, self.text(tags, a, b))
            if kind == "keep_flag":
                return self._edit(oid, ops, cat, "AI 建议（未删）· " + title,  # i18n-ignore
                                  tr("AI 没有删这段，留给你决定。") + reason, conf, sp, ai_cat,
                                  status=RESTORED, review=True)
            host = TRACK_NAMES[tags[0]] if len(tags) == 1 else self.host(tags, a, b)
            return self._edit(oid, ops, cat, title, reason, conf, sp, ai_cat, host=host)

        if kind == "tighten_pause":
            at = o["at"]
            t = self.point(at, True) + 0.005 if isinstance(at, str) else self.point(at, False)
            tags = all_tags if track == "both" else [track]
            gaps = [self.tokens[g].gap_at(t) for g in tags]
            if any(g is None for g in gaps):
                self.report.skip(oid, "停顿位置落在词内（与评分脚本一致，跳过）")  # i18n-ignore
                return None
            ga, gb = max(g[0] for g in gaps), min(g[1] for g in gaps)
            if not np.isfinite(gb):
                raise _OpError("pause has no end")
            target = max(float(o["target_s"]), 0.0)
            excess = (gb - ga) - target
            if excess < MIN_CUT_S:
                self.report.skip(oid, "停顿已经够短")  # i18n-ignore
                return None
            mid = (ga + gb) / 2
            a, b = mid - excess / 2, mid + excess / 2
            if not self.in_window(a, b):
                return self._outside(oid)
            if track != "both":
                if not self.other_silent(track, a, b):
                    self.report.skip(oid, "单轨停顿收紧（需按轨重新对时，暂不支持）")  # i18n-ignore
                    return None
                self.report.converted["单轨停顿→双轨 cut（对方无声）"] += 1  # i18n-ignore
            x, y = self.snap_range([TRACK_NAMES[g] for g in all_tags], a, b, PAUSE_SNAP_MS,
                                   bounds=(ga, gb))
            if (y - x) < MIN_CUT_S * self.sr:
                raise _OpError("range vanished after snapping")
            ops = [{"op": "cut", "start": x, "end": y, "tracks": None}]
            title = tr("停顿 {p0}s → {target}s", p0=f"{gb - ga:.1f}", target=f"{target:.1f}")
            return self._edit(oid, ops, cat, title, reason, conf, 0.0, ai_cat, host="none")

        if kind == "slip":
            if track == "both":
                raise _OpError("slip needs one track")
            a, b = self.point(o["from"], False), self.point(o["to"], True)
            delta = float(o["delta_s"])
            if b - a < MIN_CUT_S or delta == 0:
                raise _OpError("empty slip")
            if not self.in_window(min(a, a + delta), max(b, b + delta)):
                return self._outside(oid)
            name = TRACK_NAMES[track]
            x, y = self.snap_range([name], a, b, PAUSE_SNAP_MS)
            d = int(round(delta * self.sr))
            if x + d < 0:
                return self._outside(oid)
            ops = [{"op": "slip", "track": name, "start": x, "end": y, "delta": d}]
            word = self.text([track], a, b)
            title = (tr("{name} 插话挪后 {s} 秒", name=name, s=f"{abs(delta):.1f}") if delta > 0
                     else tr("{name} 插话提前 {s} 秒", name=name, s=f"{abs(delta):.1f}")) + (f" ·「{word[:10]}」" if word else "")
            return self._edit(oid, ops, cat, title, reason, conf, 0.0, ai_cat, host=name)

        raise _OpError(f"unknown op {kind!r}")

    def _outside(self, oid: str) -> None:
        self.report.skip(oid, "不在所选时间窗内")  # i18n-ignore
        return None

    def _title(self, ai_cat: str, cat: str, tags: list[str], dur: float, text: str) -> str:
        who = "" if len(tags) > 1 else tr("{p0} 单轨 · ", p0=TRACK_NAMES[tags[0]])
        quote = f" ·「{text[:14]}{'…' if len(text) > 14 else ''}」" if text else ""
        if cat == "content":
            return tr("{who}删除 {dur} 秒 · 内容删减{quote}", who=who, dur=f"{dur:.1f}", quote=quote)
        label = tr(AI_CATEGORY_LABELS.get(ai_cat, ai_cat))
        return tr("{who}{label} · {dur} 秒{quote}", who=who, label=label, dur=f"{dur:.1f}", quote=quote)

    def _edit(self, oid, ops, cat, title, reason, conf, speech_s, ai_cat, status=APPLIED,
              review=None, host=None) -> Edit:
        if review is None:
            review = needs_review(cat, conf, speech_s, kind=ai_cat, host=host, policy=self.policy)
        cons = review
        return Edit("", ops, cat, title, reason, round(conf, 2), cons, status=status, source="first_cut",
                    op_id=oid, ai_category=ai_cat, speech_s=round(speech_s, 2))

    # ---- whole document
    def convert(self, ops: list[dict]) -> list[Edit]:
        self.report.ops_in = len(ops)
        edits: list[Edit] = []
        for o in ops:
            try:
                e = self.convert_op(o)
            except (_OpError, KeyError, TypeError, ValueError) as ex:
                self.report.skip(str(o.get("id", "?")), "无法解析", str(ex))  # i18n-ignore
                continue
            if e is not None:
                edits.append(e)
        edits = self._resolve_overlaps(edits)
        edits.sort(key=lambda e: e.span[0] if e.span else -1)
        for i, e in enumerate(edits):
            e.id = f"a{i + 1:04d}"
        self.report.edits_out = len(edits)
        return edits

    def _resolve_overlaps(self, edits: list[Edit]) -> list[Edit]:
        """Ripple cuts must not overlap (the episode refuses that). Earlier-starting cuts win;
        a later one is trimmed to start where the previous ends, or dropped if nothing is left."""
        out: list[Edit] = []
        last_end = -1
        cut_edits = sorted((e for e in edits if e.cuts), key=lambda e: e.cuts[0])
        for e in cut_edits:
            o = e.ops[0]
            if o["start"] < last_end:
                if o["end"] - last_end < MIN_CUT_S * self.sr:
                    self.report.skip(e.op_id or "?", "与其他删除重叠")  # i18n-ignore
                    continue
                o["start"] = last_end
                self.report.converted["重叠删除已裁短"] += 1  # i18n-ignore
            last_end = o["end"]
            out.append(e)
        return out + [e for e in edits if not e.cuts]


def convert_ops(doc: dict | list, tokens: dict[str, TrackTokens], sr: int, w0: float = 0.0,
                w1: float = float("inf"), read: Reader | None = None,
                policy: ReviewPolicy | None = None) -> tuple[list[Edit], Report]:
    """AI ops document -> (edits in base coordinates, report). `policy`: learned review calibration
    (`learning.review_policy`), None = the defaults."""
    ops = doc["ops"] if isinstance(doc, dict) else doc
    c = Converter(tokens, sr, w0, w1, read, policy)
    edits = c.convert(ops)
    return edits, c.report


def transcript_for(tokens: dict[str, TrackTokens], w0: float, w1: float) -> dict:
    """Window-relative word list per track for the episode's read-only transcript."""
    return {"tracks": {TRACK_NAMES[tag]: [[round(t["start"] - w0, 3), round(t["end"] - w0, 3), t["t"]]
                                          for t in tr.toks if w0 <= t["start"] < w1]
                       for tag, tr in tokens.items() if tag in TRACK_NAMES}}


def build_episode(media: dict[str, MediaRef], ops_doc: dict, tokens: dict[str, TrackTokens], w0: float = 0.0,
                  w1: float | None = None, policy: ReviewPolicy | None = None) -> tuple[Project, list[Edit], dict, Report]:
    """(project, edits, transcript, report) for raw window [w0, w1) (w1 None = to the end).

    `media` maps host name (Leon / Pei) to its raw track; the base timeline is the uncut recording."""
    sr = next(iter(media.values())).sample_rate
    if any(m.sample_rate != sr for m in media.values()):
        raise ValueError("host tracks have different sample rates")
    # Each track keeps its own length: when one host's recording runs longer (a recorder stopped
    # late, an outro said alone), its tail stays in instead of being cut to the shorter track.
    end = max(m.frames for m in media.values())
    a = int(round(w0 * sr))
    b = end if w1 is None else min(int(round(w1 * sr)), end)
    if b <= a:
        raise ValueError("empty window")
    w1 = b / sr
    tracks = [Track(name, (Clip(f"{name[0]}0", ref.media_id, a, min(b, ref.frames), 0),) if ref.frames > a else ())
              for name, ref in media.items()]
    base = replace(new_timeline(sr, list(media)), tracks=tuple(tracks), next_id=1)
    project = Project({m.media_id: m for m in media.values()}, base)
    with SourcePool({m.media_id: m for m in media.values()}) as pool:
        def read(name: str, x: int, y: int):
            return pool.read(media[name].media_id, x + a, y + a)
        edits, report = convert_ops(ops_doc, tokens, sr, w0, w1, read, policy)
    return project, edits, transcript_for(tokens, w0, w1), report


def report_dict(report: Report) -> dict:
    return {"ops_in": report.ops_in, "edits_out": report.edits_out,
            "skipped": dict(report.skipped), "converted": dict(report.converted)}
