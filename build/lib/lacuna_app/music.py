"""Music on an episode: series intro/outro, interludes, beds and film clips (D45, full-play rule).

Model
-----
* The voice edit (`Episode`) is untouched. Music is a layer on top of the *voice timeline* (the
  current cut): ``<episode>/music.json`` (schema 2) lists placements.
* Everything Leon puts in plays whole, from ``src_in_s`` to ``src_out_s`` (default: the whole
  file); it is never cut short unless he trims it. Under talk it keeps playing as background,
  ``bg_db`` lower than its full level, at a constant level (docs/decisions/2026-10-18-music-full-play.md):
  - intro: from 0, full level for ``solo_s``, then down to background over ``ramp_s``; the voice
    starts there and the song plays on under it to its end.
  - interlude: at a point between two sentences (anchored in *base* samples, like edits, so it
    moves with later voice edits). The talk stops: the song rises over ``ramp_s`` (optionally it
    already played ``pre_s`` under the talk before), plays at full level for ``solo_s``, goes back
    down over ``ramp_out_s`` and the talk resumes while the song plays on as background.
  - outro: background under the last words, placed so the voice ends at ``bye_s`` of the file;
    then it rises over ``ramp_s`` and plays to ``src_out_s``, fading out over ``fade_out_s``.
  - bed: from a point (to an end point or the end of the song), constantly ``bg_db`` lower. With
    ``auto`` the App picks the point: the bed goes into the free stretches, where no other music
    plays (docs/decisions/2026-10-18-bed-auto-loop.md). With ``loop`` it repeats (crossfaded) to
    fill its stretch instead of stopping at the end of the song.
  - clip: a film line; time is inserted with ``lead_s`` of silence before and after.
* The final mix = voice tracks with the inserted gaps + one music track per placement (mono for
  preview; L/R tracks panned hard for stereo export), with fades, and `Duck`s for the background
  stretches.
* Music level is set by measurement: full level sits about 1 LU under the voice, measured on the
  part of the song that plays (levels.music_lufs); ``gain_db`` is Leon's offset on top.

Public functions used by other modules (D42): `bgm_credits`, `final_time`, `final_duration`,
`EpisodeMusic.mix` (export).
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from lacuna_core import (Clip, InsertGap, MediaRef, Previewer, Renderer, RenderSettings, SegmentCache, SourcePool,
                         Timeline, Track, validate)
from lacuna_core.master import LoudnessMeter

from .audio import HEADER_BYTES, SAMPLE_BYTES, pcm16, wav_bytes, wav_header
from .episode import ConflictError, Episode, to_base, to_tl
from .library import Library, credit_line
from .store import Workspace, atomic_write_json, read_json, now_iso as _now
from .i18n import N_, tr

SCHEMA = 2
FILE = "music.json"
APPLIED, PROPOSED = "applied", "proposed"
ROLES = {"intro": N_("片头"), "interlude": N_("间奏"), "outro": N_("片尾"), "bed": N_("铺底"), "clip": N_("台词")}
GAP_ROLES = ("interlude", "clip")            # roles that insert time into the conversation
ANCHORED = ("interlude", "clip", "bed")      # roles placed at a point of the conversation
SOLO_S = {"intro": 10.0, "interlude": 15.0}  # intro: music alone before the voice; interlude: full level in the gap
RAMP_S = 2.0                                 # rise / fall between full level and background
BG_DB = 22.0                                 # background = this much under full level (new placements)
BG_DB_V1 = 20.0                              # what a schema-1 placement was heard with
OUTRO_TAIL_S = 30.0                          # default: the voice ends this long before the outro ends
FADE_OUT_S = {"outro": 10.0}                 # fade at a trimmed end (others: 3 s)
LEAD_S = 0.5                                 # silence around a clip
LISTEN_CTX_S = 5.0                           # listening to one placement starts this long before its transition
FREE_MIN_S = 8.0                             # an automatic bed skips free stretches shorter than this
LOOP_XFADE_S = 2.0                           # crossfade where a looping bed starts over
LEVEL_LU = -1.0                              # full level vs voice loudness
CLIP_DUCK_DB = 12.0
DUCK_RAMP_S = 0.25
STEREO_HALF_DB = -3.01                       # each hard-panned half of a stereo file vs a centred mono track
TUNING = ("src_in_s", "src_out_s", "gain_db", "solo_s", "ramp_s", "ramp_out_s", "bg_db", "pre_s", "bye_s", "fade_out_s",
          "lead_s")
FLAGS = ("auto", "loop")                     # bed: placed by the App / repeats to fill its stretch
ROLE_TUNING = ("solo_s", "ramp_s", "ramp_out_s", "pre_s", "bye_s", "fade_out_s", "lead_s")   # mean something else per role
# schema 1 (before the full-play rule) cut music at these lengths and overlapped it with the voice
_V1_MAX = {"intro": 30.0, "interlude": 20.0, "outro": 60.0, "bed": 120.0, "clip": 60.0}
_V1_OVERLAP = {"intro": 4.0, "interlude": 2.0, "outro": 4.0}


@dataclass
class Placed:
    """Where one placement ended up on the final timeline (samples)."""
    p: dict
    asset: dict
    start: int
    length: int
    gap_at: int | None = None   # voice-timeline sample where time was inserted
    gap: int = 0
    anchor: int | None = None   # final-mix sample of the placement's position (anchored roles)
    bg: list[tuple[int, int]] = field(default_factory=list)   # final-mix stretches played as background
    ramp: int = 0               # samples to rise / fall between full level and background
    ramp_out: int | None = None # interlude: samples to fall back to background after the gap (None: `ramp`)
    period: int = 0             # looping bed: samples of one pass of the song (0: plays once)

    @property
    def end(self) -> int:
        return self.start + self.length


@dataclass
class Layout:
    sr: int
    voice_len: int
    inserts: list[tuple[int, int, int]] = field(default_factory=list)   # (voice sample, order, length)
    items: list[Placed] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)                  # placements whose asset is gone
    unplaced: list[dict] = field(default_factory=list)                 # automatic beds with no free stretch left

    def final(self, t: int) -> int:
        """Voice-timeline sample -> final-mix sample (material at an insert point comes after the gap)."""
        return t + sum(n for T, _, n in self.inserts if T <= t)

    def voice(self, f: int) -> int:
        """Final sample -> voice-timeline sample (a point inside inserted time maps to its insert point)."""
        shift = 0
        for T, _, n in sorted(self.inserts):
            start = T + shift
            if f < start:
                break
            if f < start + n:
                return T
            shift += n
        return f - shift

    @property
    def length(self) -> int:
        return max([self.final(self.voice_len)] + [it.end for it in self.items])


def _f(p: dict, k: str, default: float) -> float:
    v = p.get(k)
    return float(default if v is None or v == "" else v)


def layout(placements: list[dict], assets: dict[str, dict], sr: int, voice_len: int,
           to_voice) -> Layout:
    """Pure placement arithmetic. `to_voice(base_sample) -> voice sample`."""
    lay = Layout(sr, voice_len)
    live = []
    S = lambda v: int(round(v * sr))      # noqa: E731 - seconds -> samples
    for i, p in enumerate(placements):
        if p.get("status", APPLIED) != APPLIED:
            continue
        a = assets.get(p["asset_id"])
        if a is None:
            lay.skipped.append(p)
            continue
        src_in = max(0.0, float(p.get("src_in_s") or 0.0))
        src_out = min(float(p.get("src_out_s") or a["duration_s"]), a["duration_s"])
        n = S(src_out - src_in)
        if n <= S(0.05):
            lay.skipped.append(p)
            continue
        r = p["role"]
        ramp = S(max(_f(p, "ramp_s", RAMP_S), 0.0))
        solo = min(S(max(_f(p, "solo_s", SOLO_S.get(r, 0.0)), 0.0)), n)
        g = 0                           # time inserted into the conversation
        if r == "intro":
            g = solo
        elif r == "interlude":
            pre = min(S(max(_f(p, "pre_s", 0.0), 0.0)), n)
            g = min(ramp + S(max(_f(p, "ramp_out_s", _f(p, "ramp_s", RAMP_S)), 0.0)) + solo, n - pre)
        elif r == "clip":
            g = 2 * S(_f(p, "lead_s", LEAD_S)) + n
        T = None
        if r in ANCHORED and not (r == "bed" and p.get("auto")):
            T = min(max(to_voice(int(p["at_base"])), 0), voice_len)
        live.append((i, p, a, n, ramp, solo, g, T))
        if r == "intro":
            lay.inserts.append((0, -1, g))
        elif r in GAP_ROLES:
            lay.inserts.append((T, i, g))
    lay.inserts.sort()

    def gap_start(T: int, order: int) -> int:
        return T + sum(m for T2, o2, m in lay.inserts if (T2, o2) < (T, order))

    # where each piece of music plays, and which stretches of it are background; beds that fill
    # free stretches (looping, automatic) wait until everything else is placed
    later = []
    for i, p, a, n, ramp, solo, g, T in live:
        r = p["role"]
        if r == "bed" and (p.get("auto") or p.get("loop")):
            later.append((p, a, n, T))
            continue
        if r == "intro":
            it = Placed(p, a, 0, n, 0, g, bg=[(solo, n)] if solo < n else [], ramp=ramp)
        elif r == "interlude":
            gs = gap_start(T, i)
            start = max(gs - min(S(max(_f(p, "pre_s", 0.0), 0.0)), n), 0)
            bg = ([(start, gs)] if gs > start else []) + ([(gs + g, start + n)] if start + n > gs + g else [])
            ramp_out = S(max(_f(p, "ramp_out_s", _f(p, "ramp_s", RAMP_S)), 0.0))
            it = Placed(p, a, start, n, T, g, gs, bg=bg, ramp=min(ramp, g // 2), ramp_out=min(ramp_out, g // 2))
        elif r == "clip":
            lead = S(_f(p, "lead_s", LEAD_S))
            it = Placed(p, a, gap_start(T, i) + lead, n, T, g, gap_start(T, i))
        elif r == "bed":
            s = lay.final(T)
            if p.get("until_base") is not None:
                e = lay.final(min(max(to_voice(int(p["until_base"])), T), voice_len))
                n = max(min(n, e - s), S(0.05))
            it = Placed(p, a, s, n, anchor=s)
        else:   # outro: the voice ends at `bye_s` of the file
            v_end = lay.final(voice_len)
            src_in = max(0.0, float(p.get("src_in_s") or 0.0))
            src_out = src_in + n / sr
            bye = min(max(S(_f(p, "bye_s", max(src_out - OUTRO_TAIL_S, src_in)) - src_in), 0), n)
            start = max(v_end - bye, 0)
            it = Placed(p, a, start, n, bg=[(start, v_end)] if v_end > start else [], ramp=ramp)
        lay.items.append(it)
    _fill_beds(lay, later, S, to_voice)
    lay.items.sort(key=lambda it: it.start)
    return lay


def _occupied(items: list[Placed]) -> list[tuple[int, int]]:
    """Merged final-mix stretches where some music (or a clip's silence) plays."""
    spans = sorted((min(it.start, it.anchor if it.p["role"] == "clip" and it.anchor is not None else it.start),
                    max(it.end, (it.anchor or 0) + it.gap if it.p["role"] == "clip" else it.end)) for it in items)
    out: list[list[int]] = []
    for a, b in spans:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _free(occupied: list[tuple[int, int]], end: int) -> list[tuple[int, int]]:
    out, t = [], 0
    for a, b in occupied:
        if a > t:
            out.append((t, min(a, end)))
        t = max(t, b)
    if t < end:
        out.append((t, end))
    return [(a, b) for a, b in out if b > a]


def _fill_beds(lay: Layout, beds: list[tuple[dict, dict, int, int | None]], S, to_voice) -> None:
    """Looping beds at a point, then automatic beds into what is still free (in their order).
    A looping bed fills to its end point, else to where the next music starts (or the talk ends)."""
    end = lay.final(lay.voice_len)
    for p, a, n, T in [b for b in beds if not b[0].get("auto")]:
        s = lay.final(T)
        if p.get("until_base") is not None:
            e = lay.final(min(max(to_voice(int(p["until_base"])), T), lay.voice_len))
        else:
            e = min([x for x, _ in _occupied(lay.items) if x > s] + [max(end, s + n)])
        lay.items.append(Placed(p, a, s, max(e - s, S(0.05)), anchor=s, period=n))
    cursor = 0
    for p, a, n, _ in [b for b in beds if b[0].get("auto")]:
        spot = next(((max(x, cursor), y) for x, y in _free(_occupied(lay.items), end)
                     if y - max(x, cursor) >= S(FREE_MIN_S)), None)
        if spot is None:
            lay.unplaced.append(p)
            continue
        s, e = spot
        length = e - s if p.get("loop") else min(n, e - s)
        lay.items.append(Placed(p, a, s, length, anchor=s, period=n if p.get("loop") else 0))
        cursor = s + length


def speech_regions(x: np.ndarray, sr: int, threshold_db: float, start: int) -> list[tuple[int, int]]:
    """[a, b) sample ranges (offset by `start`) where `x` is louder than threshold_db (20 ms RMS),
    pauses shorter than 0.5 s bridged, blips shorter than 0.12 s dropped."""
    hop = max(1, int(0.02 * sr))
    k = len(x) // hop
    if k == 0:
        return []
    rms = np.sqrt(np.mean(x[:k * hop].reshape(k, hop).astype(np.float64) ** 2, axis=1) + 1e-12)
    on = 20 * np.log10(rms) > threshold_db
    regions: list[list[int]] = []
    i = 0
    while i < k:
        if on[i]:
            j = i
            while j < k and on[j]:
                j += 1
            if regions and i - regions[-1][1] < 25:          # < 0.5 s pause
                regions[-1][1] = j
            else:
                regions.append([i, j])
            i = j
        else:
            i += 1
    return [(start + a * hop, start + b * hop) for a, b in regions if b - a >= 6]


def upgrade_v1(p: dict, asset: dict | None) -> dict:
    """A schema-1 placement (cut at a default length, overlapping the voice) -> the full-play
    rule: a length that was only the automatic cap becomes the whole file; the voice still comes
    in (intro), resumes (interlude) and ends (outro) where it did before."""
    if "bg_db" in p or asset is None:
        return p
    r, dur = p["role"], asset["duration_s"]
    src_in = float(p.get("src_in_s") or 0.0)
    cap = min(dur, src_in + _V1_MAX.get(r, 60.0))
    old_out = float(p["src_out_s"]) if p.get("src_out_s") not in (None, "") else cap
    n = max(old_out - src_in, 0.0)
    ov = float(_V1_OVERLAP.get(r, 0.0) if p.get("overlap_s") is None else p["overlap_s"])
    ov = min(ov, n / 2 if r == "interlude" else n)
    if r == "intro":
        p["solo_s"] = round(n - ov, 3)
    elif r == "interlude":
        p["solo_s"] = round(max(n - 2 * ov - 2 * RAMP_S, 1.0), 3)
    elif r == "outro":
        p["bye_s"] = round(src_in + ov, 3)
    if abs(old_out - cap) < 0.01:
        p["src_out_s"] = dur
    p.pop("overlap_s", None)
    p["bg_db"] = BG_DB_V1 if r != "clip" else None
    return p


class EpisodeMusic:
    """Music placements of one episode, and the final mix built from them."""

    def __init__(self, ws: Workspace, ep: Episode, lib: Library | None = None):
        self.ws, self.ep = ws, ep
        self.lib = lib or Library(ws)
        self.path = ep.dir / FILE
        self.lock = threading.RLock()
        self._voice_lufs: dict[str, float] = {}
        self._mixes: dict[tuple, tuple] = {}
        self._players: dict[str, tuple] = {}
        self._clips: dict[str, bytes] = {}

    # ------------------------------------------------------------------ storage
    def load(self) -> dict:
        if not self.path.exists() and not self.path.with_name(FILE + ".bak").exists():
            return {"schema": SCHEMA, "placements": [], "series": None, "series_dismissed": False, "draft": None}
        doc = read_json(self.path)
        if doc.get("schema") == 1:
            assets = {a["id"]: a for a in self.lib.assets()}
            for p in doc["placements"] + ((doc.get("draft") or {}).get("placements") or []):
                upgrade_v1(p, assets.get(p["asset_id"]))
            doc["schema"] = SCHEMA
        if doc.get("schema") != SCHEMA:
            raise ValueError(f"unsupported music schema {doc.get('schema')}")
        return doc

    def save(self, doc: dict) -> None:
        atomic_write_json(self.path, doc, protected=tuple(Path(m.path) for m in self.ep.media.values()))

    def placements(self) -> list[dict]:
        return self.load()["placements"]

    def digest(self, placements: list[dict] | None = None) -> str:
        ps = self.placements() if placements is None else placements
        assets = {a["id"]: (a.get("lufs"), a["duration_s"]) for a in self.lib.assets()}
        return hashlib.sha1(json.dumps([ps, assets], sort_keys=True).encode()).hexdigest()[:12]

    def export_key(self) -> str:
        """Changes exactly when the music in an export would change (applied placements + their
        assets' levels), so an older export can be flagged as stale."""
        ps = [p for p in self.placements() if p.get("status", APPLIED) == APPLIED]
        used = {p["asset_id"] for p in ps}
        assets = {a["id"]: (a.get("lufs"), a["duration_s"]) for a in self.lib.assets() if a["id"] in used}
        keep = ("asset_id", "role", "at_base", "until_base", *TUNING, *FLAGS)
        return hashlib.sha1(json.dumps([[{k: p.get(k) for k in keep} for p in ps], assets],
                                       sort_keys=True).encode()).hexdigest()[:12]

    # ------------------------------------------------------------------ editing
    def _voice_to_base(self, at_s: float, enabled=None) -> int:
        enabled = self.ep.enabled if enabled is None else enabled
        cuts = self.ep.cuts_for(enabled)
        tl = self.ep.timeline_for(enabled)
        t = min(max(int(round(at_s * self.ep.sr)), 0), tl.length)
        return to_base(t, cuts)

    def final_to_voice_s(self, at_final_s: float, exclude: str | None = None,
                         placements: list[dict] | None = None) -> float:
        """Final-mix seconds -> voice-timeline seconds. `exclude`: the placement being moved, so
        its own inserted time doesn't count."""
        ps = self.placements() if placements is None else placements
        lay = self.layout(placements=[p for p in ps if p["id"] != exclude])
        return lay.voice(int(round(at_final_s * self.ep.sr))) / self.ep.sr

    def _clean(self, p: dict, asset: dict) -> dict:
        r = p["role"]
        if r not in ROLES:
            raise ConflictError(f"unknown role {r}")
        dur = asset["duration_s"]
        clamp = lambda k, default, lo, hi: round(min(max(_f(p, k, default), lo), hi), 3)   # noqa: E731
        src_in = clamp("src_in_s", 0.0, 0.0, max(dur - 0.1, 0.0))
        src_out = clamp("src_out_s", dur, src_in + 0.1, dur)      # default: the whole file
        p.update(src_in_s=src_in, src_out_s=src_out, gain_db=round(clamp("gain_db", 0.0, -30.0, 12.0), 2))
        p.pop("overlap_s", None)
        if r in ("intro", "interlude", "outro"):
            p["ramp_s"] = clamp("ramp_s", RAMP_S, 0.0, 10.0)
        if r != "clip":
            p["bg_db"] = clamp("bg_db", BG_DB, 0.0, 40.0)
            v = p.get("fade_out_s")
            p["fade_out_s"] = None if v in (None, "") else clamp("fade_out_s", 0.0, 0.0, 30.0)   # None: automatic
        if r in SOLO_S:
            p["solo_s"] = clamp("solo_s", SOLO_S[r], 0.0, 600.0)
        if r == "interlude":
            p["pre_s"] = clamp("pre_s", 0.0, 0.0, src_out - src_in)
            p["ramp_out_s"] = clamp("ramp_out_s", p["ramp_s"], 0.0, 10.0)
        if r == "outro":
            p["bye_s"] = clamp("bye_s", max(src_out - OUTRO_TAIL_S, src_in), src_in, src_out)
        if r == "clip":
            p["lead_s"] = clamp("lead_s", LEAD_S, 0.0, 5.0)
        relevant = {"solo_s": r in SOLO_S, "pre_s": r == "interlude", "ramp_out_s": r == "interlude", "bye_s": r == "outro", "lead_s": r == "clip",
                    "ramp_s": r in ("intro", "interlude", "outro"), "bg_db": r != "clip", "fade_out_s": r != "clip"}
        for k, keep in relevant.items():
            if not keep:
                p[k] = None
        for k in FLAGS:
            p[k] = bool(p.get(k)) if r == "bed" else None
        if r in ANCHORED and p.get("at_base") is None and not p.get("auto"):
            raise ConflictError(tr("间奏、台词需要一个位置"))
        if r not in ANCHORED:
            p["at_base"] = None
        if r != "bed" or p.get("auto"):
            p["until_base"] = None
        return p

    def add(self, asset_id: str, role: str, at_s: float | None = None, until_s: float | None = None,
            status: str = APPLIED, source: str = "manual", auto: bool | None = None, loop: bool = False,
            **tuning) -> dict:
        """Place an asset. `at_s` / `until_s` are seconds on the current voice timeline; `tuning`:
        any of TUNING (unset ones get the role's defaults). A bed without `at_s` is automatic: the
        App puts it into the free stretches."""
        asset = self.lib.asset(asset_id)
        if auto is None:
            auto = role == "bed" and at_s is None
        with self.lock:
            p = {"id": "mu_" + uuid.uuid4().hex[:8], "asset_id": asset_id, "role": role,
                 "at_base": self._voice_to_base(at_s) if at_s is not None and not auto else None,
                 "until_base": self._voice_to_base(until_s) if until_s is not None else None,
                 **{k: tuning.get(k) for k in TUNING}, "auto": auto, "loop": loop,
                 "status": status, "source": source, "created_at": _now()}
            p = self._clean(p, asset)
            doc = self.load()
            if role in ("intro", "outro"):        # one intro, one outro
                doc["placements"] = [x for x in doc["placements"] if x["role"] != role]
            doc["placements"].append(p)
            self.save(doc)
            return p

    def update(self, pid: str, **fields) -> dict:
        """Change a placement. A new `role` keeps the song, its trim, volume and background level
        and starts the new role's own numbers from their defaults; an automatic bed given a
        position becomes a bed at that position."""
        with self.lock:
            doc = self.load()
            p = next((x for x in doc["placements"] if x["id"] == pid), None)
            if p is None:
                raise KeyError(pid)
            role = fields.get("role")
            if role is not None and role != p["role"]:
                for k in ROLE_TUNING:
                    p[k] = None
                if role == "bed" and p["role"] not in ANCHORED:
                    p["auto"] = True          # no position yet: the App finds one
                p["role"] = role
            if "at_s" in fields:
                v = fields.pop("at_s")
                if v is not None:
                    p["at_base"] = self._voice_to_base(v)
                    p["auto"] = False
            if "until_s" in fields:
                v = fields.pop("until_s")
                p["until_base"] = self._voice_to_base(v) if v is not None else None
                if v is not None:
                    p["auto"] = False
            for k in ("asset_id", "status", *TUNING, *FLAGS):
                if k in fields and fields[k] is not None:
                    p[k] = fields[k]
            if p["role"] in ANCHORED and p.get("at_base") is None and not p.get("auto"):
                if p["role"] != "bed":
                    raise ConflictError(tr("间奏、台词需要一个位置"))
                p["auto"] = True
            if p["status"] not in (APPLIED, PROPOSED):
                raise ConflictError(f"unknown status {p['status']}")
            self._clean(p, self.lib.asset(p["asset_id"]))
            if p["role"] in ("intro", "outro"):
                doc["placements"] = [x for x in doc["placements"] if x["role"] != p["role"] or x["id"] == pid]
            self.save(doc)
            return p

    def remove(self, pid: str) -> None:
        with self.lock:
            doc = self.load()
            if not any(x["id"] == pid for x in doc["placements"]):
                raise KeyError(pid)
            doc["placements"] = [x for x in doc["placements"] if x["id"] != pid]
            self.save(doc)

    # ------------------------------------------------------------------ suggestions (draft)
    # A suggestion from "按用途自动放好" or from Claude is a full alternative placement list, kept
    # next to the real one. It is heard with `preview(..., placements=draft)` and only becomes the
    # music of the episode (and so of the export) when Leon accepts it.
    def draft(self) -> dict | None:
        return self.load().get("draft")

    def set_draft(self, placements: list[dict], changes: list[dict], message: str, source: str,
                  alternatives: dict | None = None) -> dict:
        with self.lock:
            doc = self.load()
            for p in placements:
                self._clean(p, self.lib.asset(p["asset_id"]))
            d = {"id": "dr_" + uuid.uuid4().hex[:8], "source": source, "message": message, "changes": changes,
                 "placements": placements, "alternatives": alternatives or {}, "base": self.digest(doc["placements"]),
                 "created_at": _now()}
            doc["draft"] = d
            self.save(doc)
            return d

    def accept_draft(self, draft_id: str) -> None:
        with self.lock:
            doc = self.load()
            d = doc.get("draft")
            if not d or d["id"] != draft_id:
                raise KeyError(draft_id)
            if d["base"] != self.digest(doc["placements"]):
                raise ConflictError(tr("这条建议之后配乐又改过了，建议已经过期，请重新让 LACUNA 看一次"))
            doc["placements"] = [dict(p, status=APPLIED) for p in d["placements"]]
            doc["draft"] = None
            self.save(doc)

    def discard_draft(self) -> None:
        with self.lock:
            doc = self.load()
            doc["draft"] = None
            self.save(doc)

    def move_draft(self, pid: str, voice_s: float) -> dict:
        """Pick another position (one of the offered alternatives) for a suggested placement."""
        with self.lock:
            doc = self.load()
            d = doc.get("draft")
            p = next((x for x in (d or {}).get("placements", []) if x["id"] == pid), None)
            if p is None or p["role"] not in ANCHORED:
                raise KeyError(pid)
            p["at_base"] = self._voice_to_base(voice_s)
            self.save(doc)
            return d

    def draft_view(self) -> dict | None:
        d = self.draft()
        if not d:
            return None
        lay = self.layout(placements=d["placements"])
        sr = self.ep.sr
        alts = {pid: [{"voice_s": v, "final_s": round(lay.final(int(round(v * sr))) / sr, 3)} for v in vs]
                for pid, vs in d.get("alternatives", {}).items()}
        live = {p["id"] for p in d["placements"]}
        return {"id": d["id"], "source": d["source"], "message": d["message"],
                "changes": [dict(c, previewable=c.get("pid") in live) for c in d["changes"]],
                "placements": self.items_json(lay, include_proposed=False), "duration": round(lay.length / sr, 3),
                "alternatives": alts, "stale": d["base"] != self.digest()}

    # ------------------------------------------------------------------ default opener / ending (albums.py)
    def defaults(self) -> dict:
        from .albums import Albums
        return Albums(self.ws).defaults_for(self.ep.id)

    def series_suggestion(self) -> dict | None:
        """The album's / project's default opener and ending, offered while this episode has neither:
        {"name": album name or None, "from": "album" / "project", "intro", "outro"} (asset names)."""
        doc = self.load()
        if doc.get("series_dismissed") or any(p["role"] in ("intro", "outro") for p in doc["placements"]):
            return None
        d = self.defaults()
        names = {r: (self._asset_or_none(d[r]["asset_id"]) or {}).get("name") if d[r] else None for r in ("intro", "outro")}
        if not any(names.values()):
            return None
        album = d["album"]
        return {"name": album["name"] if album else None, "from": "album" if album else "project",
                "intro": names["intro"], "outro": names["outro"],
                "intro_from": d["intro_from"], "outro_from": d["outro_from"]}

    def apply_series(self, name: str | None = None) -> list[dict]:
        """Put the default opener / ending in (`name` is ignored: an episode has one album)."""
        d = self.defaults()
        added = []
        for role in ("intro", "outro"):
            t = d.get(role)
            if t and self._asset_or_none(t["asset_id"]):
                t = upgrade_v1(dict(t, role=role), self._asset_or_none(t["asset_id"]))
                added.append(self.add(t["asset_id"], role, source="series", **{k: t.get(k) for k in TUNING}))
        if not added:
            raise ConflictError(tr("还没有默认的片头片尾"))
        with self.lock:
            doc = self.load()
            doc["series"] = (d["album"] or {}).get("name")
            self.save(doc)
        return added

    def dismiss_series(self) -> None:
        with self.lock:
            doc = self.load()
            doc["series_dismissed"] = True
            self.save(doc)

    def save_as_series(self, target: str) -> dict:
        """「设为专辑 / 项目的默认片头片尾」: this episode's opener and ending (with their tuning) become
        the default of its album (`target` "album") or of the whole project ("project")."""
        from .albums import Albums
        ps = {p["role"]: p for p in self.placements() if p.get("status", APPLIED) == APPLIED}
        if "intro" not in ps and "outro" not in ps:
            raise ConflictError(tr("这一集还没有片头或片尾"))
        albums = Albums(self.ws)
        pair = {r: ps[r] for r in ("intro", "outro") if r in ps}
        if target == "album":
            aid = albums.album_of(self.ep.id)
            if not aid:
                raise ConflictError(tr("这一集不在专辑里"))
            return albums.update(aid, **pair)
        return albums.set_project(**pair)

    def _asset_or_none(self, aid: str) -> dict | None:
        try:
            return self.lib.asset(aid)
        except KeyError:
            return None

    # ------------------------------------------------------------------ layout + mix
    def layout(self, enabled=None, placements: list[dict] | None = None) -> Layout:
        ep = self.ep
        enabled = ep.enabled if enabled is None else enabled
        with ep.lock:
            tl = ep.timeline_for(enabled)
            cuts = ep.cuts_for(enabled)
        assets = {a["id"]: a for a in self.lib.assets()}
        ps = self.placements() if placements is None else placements
        return layout(ps, assets, ep.sr, tl.length, lambda b: to_tl(b, cuts))

    def voice_lufs(self, enabled) -> float:
        """Loudness of the voice cut, from up to 12 ten-second windows spread over it."""
        ep = self.ep
        tl = ep.timeline_for(enabled)
        key = tl.digest()
        if key not in self._voice_lufs:
            meter = LoudnessMeter(ep.sr, 1, dual_mono=True, true_peak=False)
            win = int(10 * ep.sr)
            n = max(1, min(12, tl.length // win))
            for k in range(n):
                a = int((k + 0.5) * tl.length / n) - win // 2
                a = min(max(a, 0), max(tl.length - win, 0))
                meter.add(ep.render(enabled, a, min(a + win, tl.length))[:, 0])
            v = meter.integrated()
            self._voice_lufs[key] = v if math.isfinite(v) else -20.0
        return self._voice_lufs[key]

    def mix(self, enabled=None, channels: int = 1,
            placements: list[dict] | None = None) -> tuple[Timeline, dict[str, MediaRef], Layout]:
        """Final mix timeline (voice with inserted time + music tracks with fades and ducking),
        the media table it needs, and the layout. Cached per voice version + music state.
        `placements` replaces the saved ones (to hear a suggestion before it is accepted)."""
        ep = self.ep
        enabled = ep.enabled if enabled is None else enabled
        key = (enabled, self.digest(placements), channels)
        with self.lock:
            hit = self._mixes.get(key)
            if hit:
                return hit
            lay = self.layout(enabled, placements)
            with ep.lock:
                voice = ep.timeline_for(enabled)
            tl = voice
            for T, _, n in sorted(lay.inserts, reverse=True):      # latest first keeps earlier points valid
                tl = InsertGap(T, n).apply(tl)
            media = dict(ep.media)
            vl = self.voice_lufs(enabled) if lay.items else -20.0
            # where the voice speaks, on the final timeline (for ducking)
            pool = SourcePool(media)
            vr = Renderer(pool, RenderSettings(channels=1))
            tracks = list(tl.tracks)
            try:
                for it in lay.items:
                    tracks += self._music_tracks(it, tl, vr, vl, channels, media)
            finally:
                pool.close()
            tl = replace(tl, tracks=tuple(tracks))
            validate(tl, media)
            out = (tl, media, lay)
            if len(self._mixes) > 6:
                self._mixes.clear()
            self._mixes[key] = out
            return out

    def _music_tracks(self, it: Placed, voice_tl: Timeline, vr: Renderer, voice_lufs: float, channels: int,
                      media: dict[str, MediaRef]) -> list[Track]:
        from lacuna_core.edl import Duck
        sr = self.ep.sr
        p, a, r = it.p, it.asset, it.p["role"]
        src_in = int(round(p["src_in_s"] * sr))
        n = it.length
        one_pass = int(round((p["src_out_s"] - p["src_in_s"]) * sr))
        trimmed = p["src_out_s"] < a["duration_s"] - 0.05 or (r == "bed" and abs(n - one_pass) > 1)
        fo = _f(p, "fade_out_s", FADE_OUT_S.get(r, 3.0) if trimmed else 0.0)
        fo = int(round(fo * sr))
        if r == "clip":
            fi = fo = int(0.01 * sr)
        elif r == "interlude" and it.start == it.anchor:     # starts in the gap: rises from silence
            fi = it.ramp or int(0.5 * sr)
        elif it.bg and it.bg[0][0] == it.start:              # starts under the talk
            fi = int(1.5 * sr)
        else:
            fi = int(0.5 * sr) if p["src_in_s"] > 0.05 else 0
        if fi + fo > n:
            fi, fo = n // 2, n - n // 2
        gain = self.level_db(p, a, voice_lufs) + p["gain_db"]
        ducks = []
        if r == "bed":                       # the whole bed is background: simply lower
            gain -= _f(p, "bg_db", BG_DB)
        elif r == "clip":                    # a film line never plays under speech, but just in case
            lo, hi = it.start, min(it.end, voice_tl.length)
            if hi > lo:
                x = vr.render(voice_tl, lo, hi)[:, 0]
                ramp = int(DUCK_RAMP_S * sr)
                ducks = [Duck(s, e, CLIP_DUCK_DB, ramp) for s, e in speech_regions(x, sr, voice_lufs - 22.0, lo)]
        else:
            depth = _f(p, "bg_db", BG_DB)
            after_gap = (it.anchor or 0) + it.gap if r == "interlude" else None
            ducks = [Duck(s, e, depth, it.ramp_out if s == after_gap and it.ramp_out is not None else it.ramp)
                     for s, e in it.bg if e > s and depth > 0]
        layouts = [("m", 0.0, 0.0)] if channels == 1 else [("L", -1.0, STEREO_HALF_DB), ("R", 1.0, STEREO_HALF_DB)]
        out = []
        for lay_, pan, extra in layouts:
            m = self.lib.media(a, sr, lay_)
            media[m.media_id] = m
            passes = loop_passes(it.start, n, src_in, min(it.period, m.frames - src_in) if it.period else 0,
                                 fi, fo, int(LOOP_XFADE_S * sr), m.frames)
            for k in (0, 1):      # a looping bed alternates two tracks so the passes can overlap
                clips = tuple(Clip(f"{p['id']}_{lay_}" + (f"_{j}" if j else ""), m.media_id, a_, b_, st,
                                   round(gain + extra, 3), f_in, f_out)
                              for j, (a_, b_, st, f_in, f_out) in enumerate(passes) if j % 2 == k)
                if clips:
                    name = f"♪{p['id']}{'' if lay_ == 'm' else ' ' + lay_}{'' if k == 0 else ' ~'}"
                    out.append(Track(name, clips, pan=pan, ducks=tuple(ducks)))
        return out

    # ------------------------------------------------------------------ listening
    def mix_key(self, enabled=None, placements: list[dict] | None = None) -> str:
        enabled = self.ep.enabled if enabled is None else enabled
        return hashlib.sha1(("|".join(sorted(enabled)) + self.digest(placements)).encode()).hexdigest()[:16]

    def _player(self, enabled, placements: list[dict] | None = None) -> tuple[Timeline, Previewer]:
        k = self.mix_key(enabled, placements)
        hit = self._players.get(k)
        if hit is None:
            tl, media, _ = self.mix(enabled, 1, placements)
            for _, (_, pv, pool) in list(self._players.items()):
                pool.close()
            self._players.clear()
            pool = SourcePool(media)
            pv = Previewer(Renderer(pool, RenderSettings(channels=1)), SegmentCache(96 << 20), block_s=2.0)
            hit = self._players[k] = (tl, pv, pool)
        return hit[0], hit[1]

    def render(self, enabled, a: int, b: int, placements: list[dict] | None = None) -> np.ndarray:
        with self.lock:
            tl, pv = self._player(enabled, placements)
            return pv.render(tl, a, b).audio

    def wav_size(self, enabled) -> int:
        with self.lock:
            tl, _ = self._player(enabled)
            return HEADER_BYTES + tl.length * SAMPLE_BYTES

    def iter_wav(self, enabled, first: int, last: int, chunk_s: float = 4.0):
        """Bytes [first, last] of this mix version. Always exactly that many: if the music changes
        while this stream is still being read, the rest of it is silence (the page has already
        switched to the new version's URL) instead of a short body the server would abort."""
        with self.lock:
            key = self.mix_key(enabled)
            tl, _ = self._player(enabled)
        n, sr = tl.length, self.ep.sr
        want, sent = last - first + 1, 0
        head = wav_header(n, sr, 1)
        if first < HEADER_BYTES:
            chunk = head[first:min(last + 1, HEADER_BYTES)]
            sent += len(chunk)
            yield chunk
        d0, d1 = max(first - HEADER_BYTES, 0), last - HEADER_BYTES + 1
        s0, s1 = d0 // SAMPLE_BYTES, min(-(-d1 // SAMPLE_BYTES), n)
        step = int(chunk_s * sr)
        for s in range(s0, s1 if d1 > d0 else s0, step):
            e = min(s + step, s1)
            with self.lock:
                if self.mix_key(enabled) == key:
                    data = pcm16(self.render(enabled, s, e)[:, 0])
                else:
                    data = bytes((e - s) * SAMPLE_BYTES)
            lo = max(d0 - s * SAMPLE_BYTES, 0)
            hi = min(d1 - s * SAMPLE_BYTES, len(data))
            chunk = data[lo:hi][:want - sent]
            sent += len(chunk)
            yield chunk
        if sent < want:
            yield bytes(want - sent)

    def preview(self, pid: str, ctx_s: float = 8.0, max_s: float = 75.0,
                placements: list[dict] | None = None) -> tuple[bytes, float]:
        """WAV of the final mix around one placement's transitions; returns (wav, start seconds).
        `placements`: hear a suggested set instead of the saved one."""
        enabled = self.ep.enabled
        tl, _, lay = self.mix(enabled, 1, placements)
        it = next((x for x in lay.items if x.p["id"] == pid), None)
        if it is None:
            raise KeyError(pid)
        sr = self.ep.sr
        r = it.p["role"]
        a, b = transitions(it, int(ctx_s * sr), tl.length)
        if b - a > int(max_s * sr):           # long music: the way in, or for an outro the ending
            if r == "outro":
                a = b - int(max_s * sr)
            else:
                b = a + int(max_s * sr)
        return wav_bytes(self.render(enabled, a, b, placements), sr), a / sr

    # ------------------------------------------------------------------ views
    def items_json(self, lay: Layout, include_proposed: bool = True) -> list[dict]:
        """Placements for the page; `listen_s`: where on the final mix to start listening to one
        (just before its first transition)."""
        sr = self.ep.sr
        out = []
        with self.ep.lock:
            cuts = self.ep.cuts_for(self.ep.enabled)
        for it in lay.items:
            p, a = it.p, it.asset
            until = None
            if p.get("until_base") is not None:      # a bed's end point, on the final mix
                until = round(lay.final(min(max(to_tl(int(p["until_base"]), cuts), 0), lay.voice_len)) / sr, 3)
            out.append({**p, "role_label": tr(ROLES[p["role"]]), "asset_name": a.get("name"), "asset_note": a.get("note"),
                        "asset_duration_s": a["duration_s"], "credit_line": credit_line(a),
                        "credit_status": (a.get("credit") or {}).get("status", "unknown"),
                        "start_s": round(it.start / sr, 3), "end_s": round(it.end / sr, 3),
                        "voice_at_s": round(it.gap_at / sr, 3) if it.gap_at is not None else None,
                        "at_s": round(it.anchor / sr, 3) if it.anchor is not None else None,
                        "inserted_s": round(it.gap / sr, 3), "until_at_s": until, "missing": False,
                        "listen_s": round(transitions(it, int(LISTEN_CTX_S * sr), lay.length)[0] / sr, 3)})
        for p in lay.unplaced:
            a = self._asset_or_none(p["asset_id"]) or {}
            out.append({**p, "role_label": tr(ROLES[p["role"]]), "missing": False, "no_room": True,
                        "asset_name": a.get("name"), "asset_note": a.get("note"), "asset_duration_s": a.get("duration_s"),
                        "credit_line": credit_line(a) if a else "", "credit_status": (a.get("credit") or {}).get("status", "unknown"),
                        "start_s": None, "end_s": None})
        for p in lay.skipped:
            out.append({**p, "role_label": tr(ROLES.get(p["role"], p["role"])), "missing": True,
                        "asset_name": None, "credit_line": tr("素材已不在库里"), "start_s": None, "end_s": None})
        proposed = [p for p in self.placements() if p.get("status") == PROPOSED] if include_proposed else []
        for p in proposed:
            a = self._asset_or_none(p["asset_id"]) or {}
            out.append({**p, "role_label": tr(ROLES.get(p["role"], p["role"])), "missing": not a,
                        "asset_name": a.get("name"), "credit_line": credit_line(a) if a else "", "start_s": None, "end_s": None})
        vl = self.voice_lufs(self.ep.enabled) if lay.items else None
        for d, it in zip(out, lay.items):        # the automatic part of the level; gain_db is Leon's offset on top
            d["level_db"] = self.level_db(it.p, it.asset, vl)
        return out

    def level_db(self, p: dict, asset: dict, voice_lufs: float) -> float:
        """Automatic gain of a placement: the part of the song that plays sits LEVEL_LU from the voice (levels.py)."""
        from . import levels
        return levels.music_level_db(self.lib, asset, p, voice_lufs, LEVEL_LU)

    def summary(self) -> dict:
        ep = self.ep
        enabled = ep.enabled
        lay = self.layout(enabled)
        sr = ep.sr
        key = self.mix_key(enabled)
        rule = self.series_suggestion()
        return {"episode": ep.id, "placements": self.items_json(lay),
                "voice_duration": round(lay.voice_len / sr, 3), "duration": round(lay.length / sr, 3),
                "mix_version": key, "mix_url": f"/api/episodes/{ep.id}/mix/{key}.wav",
                "credits": credits(lay), "series": self.load().get("series"),
                "series_suggestion": rule, "roles": {k: tr(v) for k, v in ROLES.items()}, "draft": self.draft_view(),
                # time added to the conversation, (voice seconds, seconds), so the review player can map
                # its voice-cut playhead onto the final mix when listening with music
                "inserts": [[round(T / sr, 4), round(n / sr, 4)] for T, _, n in lay.inserts if n > 0],
                "export_key": self.export_key()}


def transitions(it: Placed, c: int, length: int) -> tuple[int, int]:
    """Final-mix [a, b) around a placement's transitions (where the music turns into background
    or back, and its end), with `c` samples of context."""
    r = it.p["role"]
    if r == "intro":
        a, b = 0, it.gap + 2 * c
    elif r == "interlude":
        a, b = it.start - c, (it.anchor or it.start) + it.gap + 2 * c
    elif r == "outro":
        v_end = it.bg[0][1] if it.bg else it.start
        a, b = v_end - 2 * c, it.end + c
    else:
        a, b = it.start - c, it.end + c
    return max(a, 0), min(b, length)


def loop_passes(start: int, n: int, src_in: int, period: int, fi: int, fo: int, xfade: int,
                frames: int) -> list[tuple[int, int, int, int, int]]:
    """(src_in, src_out, start, fade_in, fade_out) of each pass of a piece of music `n` samples
    long. Without a loop (`period` 0, or `n` fits in one pass) one pass; a loop starts the song
    over `xfade` before each pass ends, crossfading."""
    if not period or n <= period:
        b = min(src_in + n, frames)
        ln = b - src_in
        if ln <= 0:
            return []
        f_in = min(fi, ln)
        return [(src_in, b, start, f_in, min(fo, max(ln - f_in, 0)))]
    xfade = min(xfade, period // 4)
    out, t, end = [], start, start + n
    while t < end:
        ln = min(period, end - t)
        first, last = t == start, t + ln >= end
        f_in = min(fi if first else xfade, ln)
        f_out = min(fo if last else xfade, max(ln - f_in, 0))
        out.append((src_in, src_in + ln, t, f_in, f_out))
        if last:
            break
        t += period - xfade
    return out


def credits(lay: Layout) -> list[dict]:
    sr = lay.sr
    out = []
    for it in lay.items:
        a, c = it.asset, (it.asset.get("credit") or {})
        # an interlude is heard where the talk stops, even when it already played under the talk before
        start = it.anchor if it.p["role"] == "interlude" and it.anchor is not None else it.start
        out.append({"role": it.p["role"], "role_label": ROLES[it.p["role"]],
                    "start_s": round(start / sr, 3), "end_s": round(it.end / sr, 3), "asset_id": a["id"],
                    "title": c.get("title"), "artist": c.get("artist"), "composer": c.get("composer"),
                    "album": c.get("album"), "film": c.get("film"), "year": c.get("year"),
                    "credit_status": c.get("status", "unknown"), "credit_line": credit_line(a)})
    return out


# ===================================================================== contract for other modules (D42)

def _open(ws: Workspace, episode_id: str, ep: Episode | None) -> tuple[EpisodeMusic, bool]:
    if ep is not None:
        return EpisodeMusic(ws, ep), False
    return EpisodeMusic(ws, Episode(ws, episode_id)), True


def bgm_credits(ws: Workspace, episode_id: str, ep: Episode | None = None) -> list[dict]:
    """Music in effect on the episode, in final-cut order: role, role_label, start_s/end_s on the
    final mix, asset_id, title, artist, composer, album, film, year, credit_status
    (confirmed / suggested / unknown) and a printable credit_line. [] when there is no music."""
    m, opened = _open(ws, episode_id, ep)
    try:
        return credits(m.layout())
    finally:
        if opened:
            m.ep.close()


def final_time(ws: Workspace, episode_id: str, t_s: float, ep: Episode | None = None) -> float:
    """Seconds on the voice-edited timeline (Episode.summary()["duration"], edit "t") -> seconds on
    the final mix with music. Identity when the episode has no music."""
    m, opened = _open(ws, episode_id, ep)
    try:
        lay = m.layout()
        return round(lay.final(int(round(t_s * lay.sr))) / lay.sr, 3)
    finally:
        if opened:
            m.ep.close()


def final_duration(ws: Workspace, episode_id: str, ep: Episode | None = None) -> float:
    m, opened = _open(ws, episode_id, ep)
    try:
        lay = m.layout()
        return round(lay.length / lay.sr, 3)
    finally:
        if opened:
            m.ep.close()
