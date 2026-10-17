"""Music on an episode: series intro/outro, interludes, beds and film clips, with ducking (D45).

Model
-----
* The voice edit (`Episode`) is untouched. Music is a layer on top of the *voice timeline* (the
  current cut): ``<episode>/music.json`` (schema 1) lists placements.
* A placement plays ``[src_in_s, src_out_s)`` of one library asset in a role:
  - intro: from 0; the voice starts ``overlap_s`` before the music ends (music ducked, fading out).
  - interlude: at a point between two sentences (anchored in *base* samples, like edits, so it
    moves with later voice edits). Time is inserted for it; ``overlap_s`` of it sits under the
    speech before and after, ducked.
  - outro: starts ``overlap_s`` before the voice ends, ducked until the voice stops.
  - bed: under speech from a point (to an end point or the end of the segment), low and ducked.
  - clip: a film line; time is inserted with ``lead_s`` of silence before and after.
* The final mix = voice tracks with the inserted gaps + one music track per placement (mono for
  preview; L/R tracks panned hard for stereo export), with fades and `Duck`s computed from where
  the voice actually speaks (rendered energy), so the voice always stays on top.
* Music level is set by measurement: normal roles sit about 1 LU under the voice, beds 14 LU
  under; ``gain_db`` is Leon's offset on top.

Public functions used by other modules (D42): `bgm_credits`, `final_time`, `final_duration`,
`EpisodeMusic.mix` (export).
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from lacuna_core import (Clip, InsertGap, MediaRef, Previewer, Renderer, RenderSettings, SegmentCache, SourcePool,
                         Timeline, Track, validate)
from lacuna_core.master import LoudnessMeter

from .audio import HEADER_BYTES, SAMPLE_BYTES, pcm16, wav_bytes, wav_header
from .episode import ConflictError, Episode, to_base, to_tl
from .library import Library, credit_line
from .store import Workspace, atomic_write_json, read_json
from .i18n import N_, tr

SCHEMA = 1
FILE = "music.json"
APPLIED, PROPOSED = "applied", "proposed"
ROLES = {"intro": N_("片头"), "interlude": N_("间奏"), "outro": N_("片尾"), "bed": N_("铺底"), "clip": N_("台词")}
GAP_ROLES = ("interlude", "clip")            # roles that insert time into the conversation
ANCHORED = ("interlude", "clip", "bed")      # roles placed at a point of the conversation
MAX_LEN = {"intro": 30.0, "interlude": 20.0, "outro": 60.0, "bed": 120.0, "clip": 60.0}   # default length cap (s)
OVERLAP = {"intro": 4.0, "interlude": 2.0, "outro": 4.0, "bed": 0.0, "clip": 0.0}
LEAD_S = 0.5                                 # silence around a clip
LEVEL_LU = {"intro": -1.0, "interlude": -1.0, "outro": -1.0, "bed": -14.0, "clip": 0.0}   # vs voice loudness
DUCK_DB = {"intro": 15.0, "interlude": 15.0, "outro": 15.0, "bed": 8.0, "clip": 12.0}
DUCK_RAMP_S = 0.25
STEREO_HALF_DB = -3.01                       # each hard-panned half of a stereo file vs a centred mono track


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def layout(placements: list[dict], assets: dict[str, dict], sr: int, voice_len: int,
           to_voice) -> Layout:
    """Pure placement arithmetic. `to_voice(base_sample) -> voice sample`."""
    lay = Layout(sr, voice_len)
    live = []
    for i, p in enumerate(placements):
        if p.get("status", APPLIED) != APPLIED:
            continue
        a = assets.get(p["asset_id"])
        if a is None:
            lay.skipped.append(p)
            continue
        src_in = max(0.0, float(p.get("src_in_s") or 0.0))
        src_out = min(float(p.get("src_out_s") or a["duration_s"]), a["duration_s"])
        n = int(round((src_out - src_in) * sr))
        if n <= int(0.05 * sr):
            lay.skipped.append(p)
            continue
        ov = min(int(round(float(p.get("overlap_s") or 0.0) * sr)), n // 2 if p["role"] == "interlude" else n)
        T = None
        if p["role"] in ANCHORED:
            T = min(max(to_voice(int(p["at_base"])), 0), voice_len)
        live.append((i, p, a, n, ov, T))
    # 1) time inserted into the conversation
    for i, p, a, n, ov, T in live:
        if p["role"] == "intro":
            lay.inserts.append((0, -1, max(n - ov, 0)))
        elif p["role"] == "interlude":
            lay.inserts.append((T, i, max(n - 2 * ov, 0)))
        elif p["role"] == "clip":
            lead = int(round(float(p.get("lead_s", LEAD_S)) * sr))
            lay.inserts.append((T, i, lead + n + lead))
    lay.inserts.sort()

    def gap_start(T: int, order: int) -> int:
        return T + sum(m for T2, o2, m in lay.inserts if (T2, o2) < (T, order))

    # 2) where each piece of music plays
    for i, p, a, n, ov, T in live:
        r = p["role"]
        if r == "intro":
            it = Placed(p, a, 0, n, 0, max(n - ov, 0))
        elif r == "interlude":
            gap = max(n - 2 * ov, 0)
            it = Placed(p, a, max(gap_start(T, i) - ov, 0), n, T, gap, gap_start(T, i))
        elif r == "clip":
            lead = int(round(float(p.get("lead_s", LEAD_S)) * sr))
            it = Placed(p, a, gap_start(T, i) + lead, n, T, lead + n + lead, gap_start(T, i))
        elif r == "bed":
            s = lay.final(T)
            if p.get("until_base") is not None:
                e = lay.final(min(max(to_voice(int(p["until_base"])), T), voice_len))
                n = max(min(n, e - s), int(0.05 * sr))
            it = Placed(p, a, s, n, anchor=s)
        else:   # outro
            it = Placed(p, a, max(lay.final(voice_len) - ov, 0), n)
        lay.items.append(it)
    lay.items.sort(key=lambda it: it.start)
    return lay


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
        keep = ("asset_id", "role", "at_base", "until_base", "src_in_s", "src_out_s", "overlap_s", "gain_db", "lead_s")
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
        src_in = min(max(float(p.get("src_in_s") or 0.0), 0.0), max(dur - 0.1, 0.0))
        src_out = p.get("src_out_s")
        src_out = min(dur, src_in + MAX_LEN[r]) if src_out in (None, "") else min(max(float(src_out), src_in + 0.1), dur)
        p.update(src_in_s=round(src_in, 3), src_out_s=round(src_out, 3),
                 overlap_s=round(min(max(float(OVERLAP[r] if p.get("overlap_s") is None else p["overlap_s"]), 0.0),
                                     (src_out - src_in) / (2 if r == "interlude" else 1)), 3),
                 gain_db=round(min(max(float(p.get("gain_db") or 0.0), -30.0), 12.0), 2))
        if r == "clip":
            p["lead_s"] = round(min(max(float(LEAD_S if p.get("lead_s") is None else p["lead_s"]), 0.0), 5.0), 3)
        if r in ANCHORED and p.get("at_base") is None:
            raise ConflictError(tr("间奏、铺底、台词需要一个位置"))
        if r not in ANCHORED:
            p["at_base"] = None
        if r != "bed":
            p["until_base"] = None
        return p

    def add(self, asset_id: str, role: str, at_s: float | None = None, until_s: float | None = None,
            src_in_s: float | None = None, src_out_s: float | None = None, overlap_s: float | None = None,
            gain_db: float = 0.0, lead_s: float | None = None, status: str = APPLIED, source: str = "manual") -> dict:
        """Place an asset. `at_s` / `until_s` are seconds on the current voice timeline."""
        asset = self.lib.asset(asset_id)
        with self.lock:
            p = {"id": "mu_" + uuid.uuid4().hex[:8], "asset_id": asset_id, "role": role,
                 "at_base": self._voice_to_base(at_s) if at_s is not None else None,
                 "until_base": self._voice_to_base(until_s) if until_s is not None else None,
                 "src_in_s": src_in_s, "src_out_s": src_out_s, "overlap_s": overlap_s, "gain_db": gain_db,
                 "lead_s": lead_s, "status": status, "source": source, "created_at": _now()}
            p = self._clean(p, asset)
            doc = self.load()
            if role in ("intro", "outro"):        # one intro, one outro
                doc["placements"] = [x for x in doc["placements"] if x["role"] != role]
            doc["placements"].append(p)
            self.save(doc)
            return p

    def update(self, pid: str, **fields) -> dict:
        with self.lock:
            doc = self.load()
            p = next((x for x in doc["placements"] if x["id"] == pid), None)
            if p is None:
                raise KeyError(pid)
            if "at_s" in fields:
                v = fields.pop("at_s")
                if v is not None:
                    p["at_base"] = self._voice_to_base(v)
            if "until_s" in fields:
                v = fields.pop("until_s")
                p["until_base"] = self._voice_to_base(v) if v is not None else None
            for k in ("asset_id", "role", "src_in_s", "src_out_s", "overlap_s", "gain_db", "lead_s", "status"):
                if k in fields and fields[k] is not None:
                    p[k] = fields[k]
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
                raise ConflictError(tr("这条建议之后配乐又改过了，建议已经过期，请重新让 Claude 看一次"))
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

    # ------------------------------------------------------------------ series rule
    def series_suggestion(self) -> dict | None:
        """The default series intro/outro, offered while this episode has neither."""
        doc = self.load()
        if doc.get("series_dismissed") or any(p["role"] in ("intro", "outro") for p in doc["placements"]):
            return None
        return self.lib.series_rule(doc.get("series"))

    def apply_series(self, name: str | None = None) -> list[dict]:
        rule = self.lib.series_rule(name)
        if rule is None:
            raise ConflictError(tr("还没有这个系列的片头规则"))
        added = []
        for role in ("intro", "outro"):
            t = rule.get(role)
            if t and self._asset_or_none(t["asset_id"]):
                added.append(self.add(t["asset_id"], role, src_in_s=t.get("src_in_s"), src_out_s=t.get("src_out_s"),
                                      overlap_s=t.get("overlap_s"), gain_db=t.get("gain_db") or 0.0, source="series"))
        with self.lock:
            doc = self.load()
            doc["series"] = rule["name"]
            self.save(doc)
        return added

    def dismiss_series(self) -> None:
        with self.lock:
            doc = self.load()
            doc["series_dismissed"] = True
            self.save(doc)

    def save_as_series(self, name: str) -> dict:
        ps = {p["role"]: p for p in self.placements() if p.get("status", APPLIED) == APPLIED}
        if "intro" not in ps and "outro" not in ps:
            raise ConflictError(tr("这一集还没有片头或片尾"))
        rule = self.lib.save_series(name, ps.get("intro"), ps.get("outro"))
        with self.lock:
            doc = self.load()
            doc["series"] = rule["name"]
            self.save(doc)
        return rule

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
            sr = ep.sr
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
        sr = self.ep.sr
        p, a, r = it.p, it.asset, it.p["role"]
        src_in = int(round(p["src_in_s"] * sr))
        n = it.length
        ov = min(int(round(p["overlap_s"] * sr)), n)
        truncated = p["src_out_s"] < a["duration_s"] - 0.05
        fi = fo = 0
        if r in ("interlude", "outro") and ov:
            fi = ov
        elif r == "bed" or p["src_in_s"] > 0.05:
            fi = int(0.5 * sr) if r != "bed" else int(1.5 * sr)
        if r in ("intro", "interlude") and ov:
            fo = ov
        elif truncated or r == "bed":
            fo = int((3.0 if r == "outro" else 1.5) * sr)
        if r == "clip":
            fi = fo = int(0.01 * sr)
        if fi + fo > n:
            fi, fo = n // 2, n - n // 2
        gain = (voice_lufs + LEVEL_LU[r] - a["lufs"] if a.get("lufs") is not None else 0.0) + p["gain_db"]
        # ducking under the voice inside the music span
        lo, hi = it.start, min(it.end, voice_tl.length)
        ducks = []
        if hi > lo and DUCK_DB[r]:
            x = vr.render(voice_tl, lo, hi)[:, 0]
            ramp = int(DUCK_RAMP_S * sr)
            from lacuna_core.edl import Duck
            ducks = [Duck(s, e, DUCK_DB[r], ramp) for s, e in speech_regions(x, sr, voice_lufs - 22.0, lo)]
        layouts = [("m", 0.0, 0.0)] if channels == 1 else [("L", -1.0, STEREO_HALF_DB), ("R", 1.0, STEREO_HALF_DB)]
        out = []
        for lay_, pan, extra in layouts:
            m = self.lib.media(a, sr, lay_)
            media[m.media_id] = m
            src_out = min(src_in + n, m.frames)
            if src_out - src_in <= 0:
                continue
            ln = src_out - src_in
            c = Clip(f"{p['id']}_{lay_}", m.media_id, src_in, src_out, it.start, round(gain + extra, 3),
                     min(fi, ln), min(fo, max(ln - min(fi, ln), 0)))
            out.append(Track(f"♪{p['id']}{'' if lay_ == 'm' else ' ' + lay_}", (c,), pan=pan, ducks=tuple(ducks)))
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
        with self.lock:
            tl, _ = self._player(enabled)
        n, sr = tl.length, self.ep.sr
        head = wav_header(n, sr, 1)
        if first < HEADER_BYTES:
            yield head[first:min(last + 1, HEADER_BYTES)]
        d0, d1 = max(first - HEADER_BYTES, 0), last - HEADER_BYTES + 1
        if d1 <= d0:
            return
        s0, s1 = d0 // SAMPLE_BYTES, min(-(-d1 // SAMPLE_BYTES), n)
        step = int(chunk_s * sr)
        for s in range(s0, s1, step):
            e = min(s + step, s1)
            data = pcm16(self.render(enabled, s, e)[:, 0])
            lo = max(d0 - s * SAMPLE_BYTES, 0)
            hi = min(d1 - s * SAMPLE_BYTES, len(data))
            yield data[lo:hi]

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
        c = int(ctx_s * sr)
        a, b = max(it.start - c, 0), min(it.end + c, tl.length)
        if b - a > int(max_s * sr):           # long music: hear the way in and the way out
            if it.p["role"] == "outro":
                a = max(b - int(max_s * sr), 0)
            else:
                b = a + int(max_s * sr)
        return wav_bytes(self.render(enabled, a, b, placements), sr), a / sr

    # ------------------------------------------------------------------ views
    def items_json(self, lay: Layout, include_proposed: bool = True) -> list[dict]:
        sr = self.ep.sr
        out = []
        for it in lay.items:
            p, a = it.p, it.asset
            out.append({**p, "role_label": tr(ROLES[p["role"]]), "asset_name": a.get("name"), "asset_note": a.get("note"),
                        "asset_duration_s": a["duration_s"], "credit_line": credit_line(a),
                        "credit_status": (a.get("credit") or {}).get("status", "unknown"),
                        "start_s": round(it.start / sr, 3), "end_s": round(it.end / sr, 3),
                        "voice_at_s": round(it.gap_at / sr, 3) if it.gap_at is not None else None,
                        "at_s": round(it.anchor / sr, 3) if it.anchor is not None else None,
                        "inserted_s": round(it.gap / sr, 3), "missing": False})
        for p in lay.skipped:
            out.append({**p, "role_label": tr(ROLES.get(p["role"], p["role"])), "missing": True,
                        "asset_name": None, "credit_line": tr("素材已不在库里"), "start_s": None, "end_s": None})
        proposed = [p for p in self.placements() if p.get("status") == PROPOSED] if include_proposed else []
        for p in proposed:
            a = self._asset_or_none(p["asset_id"]) or {}
            out.append({**p, "role_label": tr(ROLES.get(p["role"], p["role"])), "missing": not a,
                        "asset_name": a.get("name"), "credit_line": credit_line(a) if a else "", "start_s": None, "end_s": None})
        return out

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


def credits(lay: Layout) -> list[dict]:
    sr = lay.sr
    out = []
    for it in lay.items:
        a, c = it.asset, (it.asset.get("credit") or {})
        out.append({"role": it.p["role"], "role_label": ROLES[it.p["role"]],
                    "start_s": round(it.start / sr, 3), "end_s": round(it.end / sr, 3), "asset_id": a["id"],
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
