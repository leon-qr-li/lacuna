"""Per-track, non-destructive edit decision list (EDL).

Model
-----
* A `Timeline` has a sample rate and named `Track`s. Each track is an ordered tuple of
  non-overlapping `Clip`s; a clip plays source samples [src_in, src_out) of one media id
  starting at timeline sample `start`. Gaps are silence (or room tone, see `RoomTone`).
* Everything is an integer sample count at the timeline rate; sources must be at that rate
  (`media.conform` converts foreign media once).
* Edits are immutable `Op`s (`apply(timeline) -> timeline`). An `Op` can only rearrange,
  remove or re-gain *source ranges*; nothing in the model can synthesise new audio.
* `Project` keeps an append-only log of apply/undo/redo entries; the current timeline is
  derived from it. Everything (de)serialises to JSON.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields, replace
from functools import cached_property
from typing import ClassVar, Iterable

from .media import MediaRef

SCHEMA_VERSION = 1


class EDLError(ValueError):
    """Invalid edit or timeline."""


# --------------------------------------------------------------------------- data model

@dataclass(frozen=True)
class Clip:
    id: str
    media_id: str
    src_in: int
    src_out: int
    start: int
    gain_db: float = 0.0
    fade_in: int = 0   # explicit fade length in samples (0 = automatic seam crossfade)
    fade_out: int = 0

    @property
    def length(self) -> int:
        return self.src_out - self.src_in

    @property
    def end(self) -> int:
        return self.start + self.length

    def split(self, t: int, right_id: str) -> tuple["Clip", "Clip"]:
        if not self.start < t < self.end:
            raise EDLError(f"split point {t} outside clip {self.id}")
        cut = self.src_in + (t - self.start)
        left = replace(self, src_out=cut, fade_out=0)
        right = replace(self, id=right_id, src_in=cut, start=t, fade_in=0)
        return left, right


@dataclass(frozen=True)
class Duck:
    """Additive gain change of `depth_db` over [start, end) with linear-in-dB ramps outside."""
    start: int
    end: int
    depth_db: float
    ramp: int = 0


@dataclass(frozen=True)
class RoomTone:
    """Source range of a track's own noise floor, looped to fill gaps on that track."""
    media_id: str
    src_in: int
    src_out: int
    gain_db: float = 0.0


@dataclass(frozen=True)
class Track:
    name: str
    clips: tuple[Clip, ...] = ()
    gain_db: float = 0.0
    pan: float = 0.0          # -1 left .. +1 right (stereo mix only)
    mute: bool = False
    ducks: tuple[Duck, ...] = ()
    room_tone: RoomTone | None = None

    @property
    def end(self) -> int:
        return max((c.end for c in self.clips), default=0)


@dataclass(frozen=True)
class Timeline:
    sample_rate: int
    tracks: tuple[Track, ...]
    next_id: int = 0

    @property
    def length(self) -> int:
        return max((t.end for t in self.tracks), default=0)

    def track(self, name: str) -> Track:
        for t in self.tracks:
            if t.name == name:
                return t
        raise EDLError(f"no track {name!r}")

    def with_track(self, track: Track) -> "Timeline":
        self.track(track.name)
        return replace(self, tracks=tuple(track if t.name == track.name else t for t in self.tracks))

    def find_clip(self, clip_id: str) -> tuple[Track, Clip]:
        for t in self.tracks:
            for c in t.clips:
                if c.id == clip_id:
                    return t, c
        raise EDLError(f"no clip {clip_id!r}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Timeline":
        tracks = tuple(
            Track(**{**t, "clips": tuple(Clip(**c) for c in t["clips"]),
                     "ducks": tuple(Duck(**k) for k in t["ducks"]),
                     "room_tone": RoomTone(**t["room_tone"]) if t["room_tone"] else None})
            for t in d["tracks"])
        return cls(d["sample_rate"], tracks, d["next_id"])

    def digest(self) -> str:
        return self._digest

    @cached_property
    def _digest(self) -> str:   # immutable, so computed once per instance
        return hashlib.sha256(canonical_json(self.to_dict()).encode()).hexdigest()


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def new_timeline(sample_rate: int, track_names: Iterable[str]) -> Timeline:
    return Timeline(sample_rate, tuple(Track(n) for n in track_names))


def add_source_clip(tl: Timeline, track: str, media: MediaRef, src_in: int = 0,
                    src_out: int | None = None, start: int = 0, gain_db: float = 0.0) -> Timeline:
    """Convenience for building a base timeline (before any logged ops)."""
    return InsertClip(track, media.media_id, src_in, media.frames if src_out is None else src_out,
                      start, gain_db=gain_db).apply(tl)


# --------------------------------------------------------------------------- validation

def validate(tl: Timeline, media: dict[str, MediaRef]) -> None:
    names = [t.name for t in tl.tracks]
    if len(set(names)) != len(names):
        raise EDLError("duplicate track names")
    ids: set[str] = set()
    for t in tl.tracks:
        prev_end = None
        for c in t.clips:
            if c.id in ids:
                raise EDLError(f"duplicate clip id {c.id}")
            ids.add(c.id)
            m = media.get(c.media_id)
            if m is None:
                raise EDLError(f"clip {c.id}: unknown media {c.media_id}")
            if m.sample_rate != tl.sample_rate:
                raise EDLError(f"clip {c.id}: media at {m.sample_rate} Hz, timeline {tl.sample_rate} Hz")
            if not 0 <= c.src_in < c.src_out <= m.frames:
                raise EDLError(f"clip {c.id}: source range [{c.src_in},{c.src_out}) outside 0..{m.frames}")
            if c.start < 0:
                raise EDLError(f"clip {c.id}: negative timeline start")
            if c.fade_in < 0 or c.fade_out < 0 or c.fade_in + c.fade_out > c.length:
                raise EDLError(f"clip {c.id}: fades exceed clip length")
            if prev_end is not None and c.start < prev_end:
                raise EDLError(f"track {t.name}: clip {c.id} overlaps previous clip")
            prev_end = c.end
        rt = t.room_tone
        if rt is not None:
            m = media.get(rt.media_id)
            if m is None or not 0 <= rt.src_in < rt.src_out <= m.frames:
                raise EDLError(f"track {t.name}: bad room tone range")
        for d in t.ducks:
            if d.end <= d.start or d.ramp < 0:
                raise EDLError(f"track {t.name}: bad duck {d}")


# --------------------------------------------------------------------------- clip-list primitives

def _new_id(tl: Timeline) -> tuple[str, Timeline]:
    return f"c{tl.next_id}", replace(tl, next_id=tl.next_id + 1)


def _split_at(tl: Timeline, clips: list[Clip], t: int) -> Timeline:
    """Split the clip spanning t (if any) in place; returns timeline with bumped id counter."""
    for i, c in enumerate(clips):
        if c.start < t < c.end:
            rid, tl = _new_id(tl)
            clips[i:i + 1] = c.split(t, rid)
            break
    return tl


def _lift(tl: Timeline, clips: list[Clip], a: int, b: int) -> tuple[Timeline, list[Clip], list[Clip]]:
    """Remove material in [a, b). Returns (timeline, kept, removed)."""
    tl = _split_at(tl, clips, a)
    tl = _split_at(tl, clips, b)
    kept = [c for c in clips if c.end <= a or c.start >= b]
    removed = [c for c in clips if c.start >= a and c.end <= b]
    return tl, kept, removed


def _shift(clips: Iterable[Clip], from_t: int, delta: int) -> list[Clip]:
    return [replace(c, start=c.start + delta) if c.start >= from_t else c for c in clips]


def _sorted(clips: Iterable[Clip]) -> tuple[Clip, ...]:
    return tuple(sorted(clips, key=lambda c: c.start))


def _ripple_ducks(ducks: Iterable[Duck], a: int, b: int) -> tuple[Duck, ...]:
    """Remove [a, b) from duck regions and shift later ones left."""
    n = b - a
    out = []
    for d in ducks:
        s = d.start if d.start < a else max(a, d.start - n)
        e = d.end if d.end <= a else max(a, d.end - n)
        if e > s:
            out.append(replace(d, start=s, end=e))
    return tuple(out)


# --------------------------------------------------------------------------- ops

_OPS: dict[str, type["Op"]] = {}


@dataclass(frozen=True)
class Op:
    kind: ClassVar[str] = ""

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        _OPS[cls.kind] = cls

    def apply(self, tl: Timeline) -> Timeline:
        raise NotImplementedError

    def to_dict(self) -> dict:
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        if "tracks" in d and d["tracks"] is not None:
            d["tracks"] = list(d["tracks"])
        return {"op": self.kind, **d}

    @staticmethod
    def from_dict(d: dict) -> "Op":
        d = dict(d)
        cls = _OPS[d.pop("op")]
        if d.get("tracks") is not None:
            d["tracks"] = tuple(d["tracks"])
        return cls(**d)


@dataclass(frozen=True)
class CutRange(Op):
    """Ripple-delete timeline [start, end) on `tracks` (None = all). Later material moves left
    on those tracks only, so a single-track cut also re-times that track against the others."""
    kind: ClassVar[str] = "cut"
    start: int
    end: int
    tracks: tuple[str, ...] | None = None

    def apply(self, tl):
        if self.end <= self.start:
            raise EDLError("empty cut")
        names = self.tracks or tuple(t.name for t in tl.tracks)
        for name in names:
            tr = tl.track(name)
            tl, kept, _ = _lift(tl, list(tr.clips), self.start, self.end)
            kept = _shift(kept, self.end, self.start - self.end)
            tl = tl.with_track(replace(tr, clips=_sorted(kept),
                                       ducks=_ripple_ducks(tr.ducks, self.start, self.end)))
        return tl


@dataclass(frozen=True)
class LiftRange(Op):
    """Delete [start, end) on one track only, leaving a gap (no re-timing)."""
    kind: ClassVar[str] = "lift"
    track: str
    start: int
    end: int

    def apply(self, tl):
        if self.end <= self.start:
            raise EDLError("empty lift")
        tr = tl.track(self.track)
        tl, kept, _ = _lift(tl, list(tr.clips), self.start, self.end)
        return tl.with_track(replace(tr, clips=_sorted(kept)))


@dataclass(frozen=True)
class SlipRegion(Op):
    """Move the material of one track in [start, end) by `delta` samples on the timeline.
    The vacated span becomes a gap; material already at the destination is overwritten
    (that is how an interjection is slid into the other host's pause)."""
    kind: ClassVar[str] = "slip"
    track: str
    start: int
    end: int
    delta: int

    def apply(self, tl):
        if self.end <= self.start:
            raise EDLError("empty slip")
        if self.start + self.delta < 0:
            raise EDLError("slip before timeline start")
        tr = tl.track(self.track)
        tl, rest, moving = _lift(tl, list(tr.clips), self.start, self.end)
        tl, rest, _ = _lift(tl, rest, self.start + self.delta, self.end + self.delta)
        moved = [replace(c, start=c.start + self.delta) for c in moving]
        return tl.with_track(replace(tr, clips=_sorted(rest + moved)))


@dataclass(frozen=True)
class TrimClip(Op):
    """Move one edge of a clip by `delta` samples (positive = later). The material that stays
    keeps its timeline position (no ripple); validation rejects overlaps / out-of-source."""
    kind: ClassVar[str] = "trim"
    clip_id: str
    edge: str      # "in" | "out"
    delta: int

    def apply(self, tl):
        tr, c = tl.find_clip(self.clip_id)
        if self.edge == "in":
            new = replace(c, src_in=c.src_in + self.delta, start=c.start + self.delta)
        elif self.edge == "out":
            new = replace(c, src_out=c.src_out + self.delta)
        else:
            raise EDLError("edge must be 'in' or 'out'")
        if new.length <= 0:
            raise EDLError("trim removes the whole clip")
        return tl.with_track(replace(tr, clips=_sorted(new if x.id == c.id else x for x in tr.clips)))


@dataclass(frozen=True)
class InsertClip(Op):
    """Place a source range at `at` on `track`. With `ripple`, every track opens a gap of the
    clip's length at `at` first (e.g. an intro jingle that pushes the conversation later)."""
    kind: ClassVar[str] = "insert"
    track: str
    media_id: str
    src_in: int
    src_out: int
    at: int
    gain_db: float = 0.0
    fade_in: int = 0
    fade_out: int = 0
    ripple: bool = False

    def apply(self, tl):
        n = self.src_out - self.src_in
        if n <= 0:
            raise EDLError("empty insert")
        if self.ripple:
            for tr in tl.tracks:
                clips = list(tr.clips)
                tl = _split_at(tl, clips, self.at)
                ducks = tuple(replace(d, start=d.start + n, end=d.end + n) if d.start >= self.at else d
                              for d in tr.ducks)
                tl = tl.with_track(replace(tr, clips=_sorted(_shift(clips, self.at, n)), ducks=ducks))
        cid, tl = _new_id(tl)
        tr = tl.track(self.track)
        clip = Clip(cid, self.media_id, self.src_in, self.src_out, self.at, self.gain_db,
                    self.fade_in, self.fade_out)
        return tl.with_track(replace(tr, clips=_sorted(tr.clips + (clip,))))


@dataclass(frozen=True)
class SetTrackGain(Op):
    kind: ClassVar[str] = "track_gain"
    track: str
    gain_db: float

    def apply(self, tl):
        return tl.with_track(replace(tl.track(self.track), gain_db=self.gain_db))


@dataclass(frozen=True)
class SetClipGain(Op):
    kind: ClassVar[str] = "clip_gain"
    clip_id: str
    gain_db: float

    def apply(self, tl):
        tr, c = tl.find_clip(self.clip_id)
        return tl.with_track(replace(tr, clips=tuple(
            replace(x, gain_db=self.gain_db) if x.id == c.id else x for x in tr.clips)))


@dataclass(frozen=True)
class SetFades(Op):
    kind: ClassVar[str] = "fades"
    clip_id: str
    fade_in: int
    fade_out: int

    def apply(self, tl):
        tr, c = tl.find_clip(self.clip_id)
        return tl.with_track(replace(tr, clips=tuple(
            replace(x, fade_in=self.fade_in, fade_out=self.fade_out) if x.id == c.id else x
            for x in tr.clips)))


@dataclass(frozen=True)
class AddDuck(Op):
    """Gain/ducking automation: lower `track` by depth_db over [start, end) with ramps."""
    kind: ClassVar[str] = "duck"
    track: str
    start: int
    end: int
    depth_db: float
    ramp: int = 0

    def apply(self, tl):
        tr = tl.track(self.track)
        return tl.with_track(replace(tr, ducks=tr.ducks + (Duck(self.start, self.end, self.depth_db, self.ramp),)))


@dataclass(frozen=True)
class SetRoomTone(Op):
    kind: ClassVar[str] = "room_tone"
    track: str
    media_id: str | None
    src_in: int = 0
    src_out: int = 0
    gain_db: float = 0.0

    def apply(self, tl):
        rt = RoomTone(self.media_id, self.src_in, self.src_out, self.gain_db) if self.media_id else None
        return tl.with_track(replace(tl.track(self.track), room_tone=rt))


# --------------------------------------------------------------------------- project + history

@dataclass
class Project:
    """Media table + base timeline + append-only op log. `timeline` is derived state."""
    media: dict[str, MediaRef]
    base: Timeline
    log: list[dict] = field(default_factory=list)   # {"seq", "action": apply|undo|redo, "op"?}

    def __post_init__(self):
        validate(self.base, self.media)
        self._replay()

    def _replay(self) -> None:
        self._stack: list[tuple[Op, Timeline]] = []
        self._redo: list[Op] = []
        for e in self.log:
            self._step(e)

    def _step(self, e: dict) -> None:
        if e["action"] == "apply":
            op = Op.from_dict(e["op"])
            tl = op.apply(self.timeline)
            validate(tl, self.media)
            self._stack.append((op, tl))
            self._redo.clear()
        elif e["action"] == "undo":
            if not self._stack:
                raise EDLError("nothing to undo")
            self._redo.append(self._stack.pop()[0])
        elif e["action"] == "redo":
            if not self._redo:
                raise EDLError("nothing to redo")
            op = self._redo.pop()
            self._stack.append((op, op.apply(self.timeline)))
        else:
            raise EDLError(f"bad log action {e['action']}")

    def _append(self, entry: dict) -> None:
        entry = {"seq": len(self.log), **entry}
        self._step(entry)          # raises before anything is recorded
        self.log.append(entry)

    @property
    def timeline(self) -> Timeline:
        return self._stack[-1][1] if self._stack else self.base

    @property
    def version(self) -> int:
        return len(self.log)

    @property
    def ops(self) -> list[Op]:
        return [op for op, _ in self._stack]

    def apply(self, op: Op) -> Timeline:
        self._append({"action": "apply", "op": op.to_dict()})
        return self.timeline

    def undo(self) -> Timeline:
        self._append({"action": "undo"})
        return self.timeline

    def redo(self) -> Timeline:
        self._append({"action": "redo"})
        return self.timeline

    def at_version(self, version: int) -> Timeline:
        return Project(self.media, self.base, self.log[:version]).timeline

    def to_json(self) -> str:
        return json.dumps({"schema": SCHEMA_VERSION,
                           "media": [m.to_dict() for m in self.media.values()],
                           "base": self.base.to_dict(), "log": self.log},
                          ensure_ascii=False, indent=1)

    @classmethod
    def from_json(cls, s: str) -> "Project":
        d = json.loads(s)
        if d.get("schema") != SCHEMA_VERSION:
            raise EDLError(f"unsupported schema {d.get('schema')}")
        media = {m["media_id"]: MediaRef.from_dict(m) for m in d["media"]}
        return cls(media, Timeline.from_dict(d["base"]), d["log"])
