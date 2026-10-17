"""One episode: source media, the AI first cut as a list of reviewable edits, history, rendering.

Model
-----
* The lacuna_core `Project` base timeline is the *uncut* recording (both tracks in sync).
* Every edit (first-cut or chat) holds lacuna_core op dicts expressed in **base** coordinates:
  `cut` (ripple, all tracks), `lift` (one track, no ripple), `slip` (move one track's range,
  no ripple) or `track_gain`.
* An edit's status is applied / restored / proposed / discarded. The current timeline is derived
  from the applied set: gains, then slips, then lifts, then cuts from latest to earliest - so base
  coordinates stay valid and any edit can be restored independently of the others.
  Overlapping cuts are refused.
* History is an undo/redo stack of field changes on edits (status / approved), persisted.
* `state.json` stores the lacuna_core Project (media + base + the derived op log, i.e. the
  exact render recipe), the edit list and the history, written atomically.
"""
from __future__ import annotations

import bisect
import hashlib
import threading
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import cached_property
from pathlib import Path

import numpy as np

from lacuna_core import (EDLError, MediaRef, Previewer, Project, Renderer, RenderSettings, SegmentCache, SourcePool, Timeline,
                         apply_batch, validate)
from lacuna_core.edl import SCHEMA_VERSION as PROJECT_SCHEMA
from lacuna_core.edl import Op
from lacuna_core.refine import snap_cut

from . import analysis
from .audio import HEADER_BYTES, SAMPLE_BYTES, pcm16, wav_bytes, wav_header
from .review import review_sort_key
from .editor import ChatContext, EditorAdapter, Proposal, Utterance, Word
from .store import CHAT_FILE, META_FILE, STATE_FILE, Workspace, atomic_write_json, read_json

STATE_SCHEMA = 1
APPLIED, RESTORED, PROPOSED, DISCARDED = "applied", "restored", "proposed", "discarded"

CATEGORY_LABELS = {
    "pause": "停顿收紧",
    "filler": "口误与无意识重复",
    "crosstalk": "单轨杂声（压在对方说话下）",
    "single_track": "单轨删减",
    "content": "内容删除",
    "interjection": "插话处理",
    "loudness": "响度匹配",
    "chat": "聊天修改",
}


class ConflictError(ValueError):
    """The requested change cannot be applied (overlap, nothing to undo, wrong state ...)."""


@dataclass
class Edit:
    id: str
    ops: list[dict]
    category: str
    title: str
    reason: str = ""
    confidence: float = 0.5
    consequential: bool = False
    status: str = APPLIED
    approved: bool = False
    source: str = "first_cut"
    op_id: str | None = None        # id of the AI editor op this edit came from
    ai_category: str | None = None  # the AI editor's own category (finer than `category`)
    speech_s: float = 0.0           # seconds of speech (ASR words) this edit removes

    @property
    def cuts(self) -> list[tuple[int, int]]:
        return [(o["start"], o["end"]) for o in self.ops if o["op"] == "cut"]

    @property
    def span(self) -> tuple[int, int] | None:
        s = [(o["start"], o["end"]) for o in self.ops if "start" in o]
        return (min(a for a, _ in s), max(b for _, b in s)) if s else None

    @property
    def tracks(self) -> list[str] | None:
        ts = {o.get("track") for o in self.ops if o["op"] in ("lift", "slip")}
        return sorted(ts) if ts and not self.cuts else None


@dataclass
class Clip:
    """A rendered A/B excerpt kept briefly in memory for the browser to fetch."""
    wav: bytes
    start: float
    edit_at: float
    edit_len: float


def _key(enabled: frozenset[str]) -> str:
    return hashlib.sha1("|".join(sorted(enabled)).encode()).hexdigest()[:16]


class Cuts(list):
    """Sorted, non-overlapping cut ranges with a prefix sum so `to_tl` is O(log n)."""

    @cached_property
    def _index(self) -> tuple[list[int], list[int]]:
        starts, pre = [], [0]
        for a, b in self:
            starts.append(a)
            pre.append(pre[-1] + (b - a))
        return starts, pre


def to_tl(x: int, cuts: list[tuple[int, int]]) -> int:
    """Base sample -> timeline sample under `cuts` (sorted, non-overlapping)."""
    if isinstance(cuts, Cuts):
        starts, pre = cuts._index
        i = bisect.bisect_left(starts, x)          # cuts[:i] start before x
        if i == 0:
            return x
        a, b = cuts[i - 1]
        return x - pre[i - 1] - (min(b, x) - a)
    t = x
    for a, b in cuts:
        if a >= x:
            break
        t -= min(b, x) - a
    return t


def to_base(t: int, cuts: list[tuple[int, int]], right: bool = True) -> int:
    """Timeline sample -> base sample. At a cut point `right` picks the material after it."""
    x = t
    for a, b in cuts:
        if a < x or (a == x and right):
            x += b - a
        else:
            break
    return x


def subtract(a: int, b: int, cuts: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """[a, b) minus the cut ranges."""
    out, cur = [], a
    for ca, cb in cuts:
        if cb <= cur or ca >= b:
            continue
        if ca > cur:
            out.append((cur, ca))
        cur = max(cur, cb)
    if cur < b:
        out.append((cur, b))
    return out


class Episode:
    def __init__(self, ws: Workspace, episode_id: str):
        self.id = episode_id
        self.dir = ws.episode_dir(episode_id)
        self.lock = threading.RLock()
        self.meta = read_json(self.dir / META_FILE)
        st = read_json(self.dir / STATE_FILE)
        if st.get("schema") != STATE_SCHEMA:
            raise ValueError(f"unsupported state schema {st.get('schema')}")
        pj = st["project"]
        if pj.get("schema") != PROJECT_SCHEMA:
            raise ValueError(f"unsupported project schema {pj.get('schema')}")
        # the stored op log is derived state (the render recipe); the timeline is re-derived from
        # base + applied edits, so it is not replayed here
        self.media: dict[str, MediaRef] = {m["media_id"]: MediaRef.from_dict(m) for m in pj["media"]}
        self.base: Timeline = Timeline.from_dict(pj["base"])
        validate(self.base, self.media)
        self.sr = self.base.sample_rate
        self.edits: dict[str, Edit] = {e["id"]: Edit(**e) for e in st["edits"]}
        self.history: dict[str, list] = st.get("history") or {"undo": [], "redo": []}
        self.proposals: dict[str, dict] = st.get("proposals") or {}
        self.transcript = self._load_transcript()
        self._chat_log: list[dict] = self._load_chat()   # chat turns, saved to chat.json
        self._timelines: OrderedDict[frozenset, Timeline] = OrderedDict()
        self._versions: OrderedDict[str, frozenset] = OrderedDict()
        self._clips: OrderedDict[str, Clip] = OrderedDict()
        self._pool: SourcePool | None = None
        self._previewer: Previewer | None = None
        self.timeline_for(self.enabled)   # validates

    # ------------------------------------------------------------------ derivation
    @property
    def enabled(self) -> frozenset[str]:
        return frozenset(e.id for e in self.edits.values() if e.status == APPLIED)

    def ops_for(self, enabled: frozenset[str]) -> list[dict]:
        es = [self.edits[i] for i in sorted(enabled)]
        ops = [o for e in es for o in e.ops]
        gains = [o for o in ops if o["op"] not in ("cut", "lift", "slip")]
        slips = sorted((o for o in ops if o["op"] == "slip"), key=lambda o: (o["start"], o["track"]))
        lifts = sorted((o for o in ops if o["op"] == "lift"), key=lambda o: (o["start"], o["track"]))
        cuts = sorted((o for o in ops if o["op"] == "cut"), key=lambda o: -o["start"])
        return gains + slips + lifts + cuts

    def cuts_for(self, enabled: frozenset[str]) -> Cuts:
        cs = Cuts(sorted(c for i in enabled for c in self.edits[i].cuts))
        for (a0, b0), (a1, b1) in zip(cs, cs[1:]):
            if a1 < b0:
                raise ConflictError("两处删除重叠，不能同时应用")
        return cs

    def project_dict(self, enabled: frozenset[str]) -> dict:
        """lacuna_core Project JSON (media + base + op log): the exact render recipe of a version.
        `Project.from_json` of it replays to the same timeline as `timeline_for`."""
        log = [{"seq": i, "action": "apply", "op": o} for i, o in enumerate(self.ops_for(enabled))]
        return {"schema": PROJECT_SCHEMA, "media": [m.to_dict() for m in self.media.values()],
                "base": self.base.to_dict(), "log": log}

    def _derive(self, enabled: frozenset[str]) -> Timeline:
        self.cuts_for(enabled)
        try:
            tl = apply_batch(self.base, [Op.from_dict(o) for o in self.ops_for(enabled)])
            validate(tl, self.media)
        except (EDLError, KeyError, TypeError) as e:
            raise ConflictError(f"改动无法应用：{e}") from e
        return tl

    def timeline_for(self, enabled: frozenset[str]) -> Timeline:
        tl = self._timelines.get(enabled)
        if tl is None:
            tl = self._derive(enabled)
            self._timelines[enabled] = tl
            while len(self._timelines) > 24:
                self._timelines.popitem(last=False)
        else:
            self._timelines.move_to_end(enabled)
        return tl

    def version_key(self, enabled: frozenset[str] | None = None) -> str:
        enabled = self.enabled if enabled is None else enabled
        k = _key(enabled)
        self._versions[k] = enabled
        self._versions.move_to_end(k)
        while len(self._versions) > 32:
            self._versions.popitem(last=False)
        return k

    def enabled_for_key(self, key: str) -> frozenset[str] | None:
        return self._versions.get(key)

    # ------------------------------------------------------------------ rendering
    @property
    def previewer(self) -> Previewer:
        if self._previewer is None:
            self._pool = SourcePool(self.media)
            self._previewer = Previewer(Renderer(self._pool, RenderSettings(channels=1)),
                                        SegmentCache(192 << 20), block_s=2.0)
        return self._previewer

    def render(self, enabled: frozenset[str], a: int, b: int) -> np.ndarray:
        with self.lock:
            return self.previewer.render(self.timeline_for(enabled), a, b).audio

    def wav_size(self, enabled: frozenset[str]) -> int:
        return HEADER_BYTES + self.timeline_for(enabled).length * SAMPLE_BYTES

    def iter_wav(self, enabled: frozenset[str], first: int, last: int, chunk_s: float = 4.0):
        """Bytes [first, last] (inclusive) of the WAV of this version, rendered on demand."""
        n = self.timeline_for(enabled).length
        head = wav_header(n, self.sr, 1)
        if first < HEADER_BYTES:
            yield head[first:min(last + 1, HEADER_BYTES)]
        d0, d1 = max(first - HEADER_BYTES, 0), last - HEADER_BYTES + 1      # data byte range
        if d1 <= d0:
            return
        s0, s1 = d0 // SAMPLE_BYTES, min(-(-d1 // SAMPLE_BYTES), n)
        step = int(chunk_s * self.sr)
        for s in range(s0, s1, step):
            e = min(s + step, s1)
            data = pcm16(self.render(enabled, s, e)[:, 0])
            lo = max(d0 - s * SAMPLE_BYTES, 0)
            hi = min(d1 - s * SAMPLE_BYTES, len(data))
            yield data[lo:hi]

    def ab(self, before: frozenset[str], after: frozenset[str], span: tuple[int, int] | None,
           ctx_s: float = 10.0, max_s: float = 80.0) -> dict:
        a, b = span or (0, 0)
        out = {}
        for side, enabled in (("before", before), ("after", after)):
            tl = self.timeline_for(enabled)
            cuts = self.cuts_for(enabled)
            ta, tb = to_tl(a, cuts), to_tl(b, cuts)
            c = int(ctx_s * self.sr)
            start, end = max(ta - c, 0), min(max(tb, ta) + c, tl.length)
            end = min(end, start + int(max_s * self.sr))
            audio = self.render(enabled, start, end)
            cid = uuid.uuid4().hex[:12]
            self._clips[cid] = Clip(wav_bytes(audio, self.sr), start / self.sr,
                                    (ta - start) / self.sr, (tb - ta) / self.sr)
            while len(self._clips) > 24:
                self._clips.popitem(last=False)
            out[side] = {"url": f"/api/episodes/{self.id}/clips/{cid}.wav",
                         "start": round(start / self.sr, 3),
                         "edit_at": round((ta - start) / self.sr, 3),
                         "edit_len": round((tb - ta) / self.sr, 3),
                         "duration": round((end - start) / self.sr, 3)}
        return out

    def clip(self, cid: str) -> Clip | None:
        return self._clips.get(cid)

    def edit_ab(self, eid: str) -> dict:
        e = self._edit(eid)
        return self.ab(self.enabled - {eid}, self.enabled | {eid}, e.span)

    def proposal_ab(self, pid: str) -> dict:
        p = self._proposal(pid)
        after = self._enabled_after(p["changes"])
        span = self.edits[p["target"]].span
        return self.ab(self.enabled, after, span)

    # ------------------------------------------------------------------ mutations
    def _edit(self, eid: str) -> Edit:
        if eid not in self.edits:
            raise KeyError(eid)
        return self.edits[eid]

    def _proposal(self, pid: str) -> dict:
        if pid not in self.proposals:
            raise KeyError(pid)
        return self.proposals[pid]

    def _enabled_after(self, changes: list[dict]) -> frozenset[str]:
        en = set(self.enabled)
        for c in changes:
            if c["field"] == "status":
                (en.add if c["new"] == APPLIED else en.discard)(c["id"])
        return frozenset(en)

    def _set(self, changes: list[dict], key: str) -> None:
        for c in changes:
            setattr(self.edits[c["id"]], c["field"], c[key])

    def change(self, label: str, changes: list[tuple[str, str, object]]) -> None:
        """Apply field changes to edits as one undoable step."""
        with self.lock:
            rec = [{"id": i, "field": f, "old": getattr(self._edit(i), f), "new": v} for i, f, v in changes]
            rec = [c for c in rec if c["old"] != c["new"]]
            if not rec:
                return
            self.timeline_for(self._enabled_after(rec))      # raises ConflictError if invalid
            self._set(rec, "new")
            self.history["undo"].append({"label": label, "changes": rec})
            self.history["redo"].clear()
            self.save()

    def undo(self) -> str:
        return self._step("undo", "redo", "old")

    def redo(self) -> str:
        return self._step("redo", "undo", "new")

    def _step(self, src: str, dst: str, key: str) -> str:
        with self.lock:
            if not self.history[src]:
                raise ConflictError("没有可以撤销的操作" if src == "undo" else "没有可以重做的操作")
            entry = self.history[src][-1]
            target = [{"id": c["id"], "field": c["field"], "new": c[key]} for c in entry["changes"]]
            self.timeline_for(self._enabled_after(target))
            self.history[src].pop()
            self._set(entry["changes"], key)
            self.history[dst].append(entry)
            self.save()
            return entry["label"]

    def review(self, eid: str, action: str) -> None:
        e = self._edit(eid)
        if e.status not in (APPLIED, RESTORED):
            raise ConflictError("这处改动还没有生效")
        if action == "keep":
            self.change(f"保留：{e.title}", [(eid, "status", APPLIED), (eid, "approved", True)])
        elif action == "restore":
            self.change(f"恢复：{e.title}", [(eid, "status", RESTORED), (eid, "approved", True)])
        elif action == "apply":
            self.change(f"重新应用：{e.title}", [(eid, "status", APPLIED)])
        else:
            raise ConflictError(f"unknown action {action}")

    def pending_ids(self) -> list[str]:
        """Edits that still wait for Leon's judgement (in effect or not): what `pending_review` counts."""
        return [i for i, e in self.edits.items()
                if e.consequential and not e.approved and e.status in (APPLIED, RESTORED)]

    def review_all(self, action: str, ids: list[str] | None = None) -> int:
        """Batch review as ONE undoable step. `approve` signs off each edit's current state (an applied cut stays
        cut, an unapplied AI suggestion stays unapplied); `keep` / `restore` force every edit to applied /
        restored. `ids` defaults to every edit still pending review. Returns how many edits changed."""
        if action not in ("approve", "keep", "restore"):
            raise ConflictError(f"unknown action {action}")
        targets = self.pending_ids() if ids is None else list(dict.fromkeys(ids))
        changes: list[tuple[str, str, object]] = []
        for eid in targets:
            e = self._edit(eid)
            if e.status not in (APPLIED, RESTORED):
                raise ConflictError("这处改动还没有生效")
            if action != "approve":
                changes.append((eid, "status", APPLIED if action == "keep" else RESTORED))
            changes.append((eid, "approved", True))
        n = len({i for i, f, v in changes if getattr(self.edits[i], f) != v})
        label = {"approve": "全部通过", "keep": "全部保留删除", "restore": "全部恢复原话"}[action]
        self.change(f"{label}（{n} 处）", changes)
        return n

    def add_edit(self, ops: list[dict], category: str, title: str, reason: str = "",
                 confidence: float = 1.0, source: str = "manual", status: str = PROPOSED) -> Edit:
        for o in ops:
            try:
                Op.from_dict(o)    # shape check
            except (KeyError, TypeError) as e:
                raise ValueError(f"malformed op {o!r}") from e
            if o["op"] not in ("cut", "lift", "slip", "track_gain"):
                raise ConflictError(f"op {o['op']} is not supported in this slice")
        with self.lock:
            eid = f"{'x' if source == 'chat' else 'm'}{len(self.edits) + 1:04d}"
            while eid in self.edits:
                eid += "_"
            e = Edit(eid, ops, category, title, reason, confidence,
                     consequential=category in ("content", "interjection"), status=status, source=source)
            self.edits[eid] = e
            return e

    def apply_op(self, op: dict, title: str, reason: str = "") -> Edit:
        """Directly apply a base-coordinate op as a new, undoable edit."""
        e = self.add_edit([op], "chat", title, reason, source="manual")
        try:
            self.change(f"应用：{title}", [(e.id, "status", APPLIED), (e.id, "approved", True)])
        except ConflictError:
            del self.edits[e.id]
            raise
        return e

    # ------------------------------------------------------------------ chat
    CHAT_RADIUS_S = 45.0       # transcript / pauses the editor sees around the playhead
    CHAT_HISTORY = 6           # earlier turns sent along ("再短一点", "不是这句")
    CHAT_KEEP = 2000           # turns kept in chat.json (learning reads them after export)

    def chat_context(self, text: str, playhead_s: float) -> tuple[ChatContext, dict]:
        """What the editor sees around the playhead, plus what is needed to turn its answer into
        a proposal on exactly this version of the timeline."""
        with self.lock:
            enabled = self.enabled
            tl = self.timeline_for(enabled)
            cuts = self.cuts_for(enabled)
            dur = tl.length / self.sr
            t = min(max(playhead_s, 0.0), dur)
            lo, hi = max(t - self.CHAT_RADIUS_S, 0.0), min(t + self.CHAT_RADIUS_S, dur)
            mix = self.render(enabled, int(lo * self.sr), int(hi * self.sr))[:, 0]
            runs = analysis.quiet_runs(mix, self.sr, lo)
            near = [self.edit_json(self.edits[i], cuts) | {"removed_text": self.removed_text(i)}
                    for i in self._near(t, 30.0, cuts)]
            ctx = ChatContext(text, t, dur, runs, analysis.speech_around(runs, t, max(t - 20, lo), min(t + 20, hi)),
                              near, self.transcript_text(to_base(int(t * self.sr), cuts) / self.sr),
                              self.utterances(lo, hi, enabled, cuts), self.chat_history())
            return ctx, {"enabled": enabled, "cuts": cuts, "mix": mix, "lo": lo}

    def chat(self, text: str, playhead_s: float, adapter: EditorAdapter) -> dict:
        ctx, view = self.chat_context(text, playhead_s)
        prop = adapter.propose(ctx)          # may take seconds (network): not under the lock
        notes = list(prop.notes)
        with self.lock:
            if self.enabled != view["enabled"]:
                proposal = None
                notes.append("刚才时间线有变化，这个建议作废了，请再说一次。")
            else:
                proposal, why = self._make_proposal(prop, view["cuts"], view["mix"], view["lo"])
                if why:
                    notes.append(why)
            self.log_turn(text, ctx.playhead, prop.message, proposal)
            return {"reply": prop.message, "notes": notes, "adapter": adapter.name,
                    "proposal": proposal, "usage": prop.usage}

    def chat_history(self) -> list[dict]:
        out = []
        for turn in self._chat_log[-self.CHAT_HISTORY:]:
            pid = turn.get("proposal")
            outcome = "no change proposed"
            if pid:
                outcome = {"pending": "proposed, not decided yet", "approved": "proposed and approved",
                           "discarded": "proposed and rejected"}.get(turn.get("state", "pending"), "proposed")
            out.append({"said": turn["said"], "at": turn["at"], "you_replied": turn["reply"], "outcome": outcome})
        return out

    def log_turn(self, said: str, at: float, reply: str, proposal: dict | None = None, **extra) -> None:
        with self.lock:
            self._chat_log.append({"said": said, "at": round(at, 2), "reply": reply,
                                   "proposal": proposal["id"] if proposal else None, "state": "pending",
                                   "time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **extra})
            del self._chat_log[:-self.CHAT_KEEP]
            self._save_chat()

    def _turn_state(self, pid: str, state: str) -> None:
        for turn in self._chat_log:
            if turn["proposal"] == pid:
                turn["state"] = state
        self._save_chat()

    def chat_log(self) -> list[dict]:
        with self.lock:
            return [dict(t) for t in self._chat_log]

    def _load_chat(self) -> list[dict]:
        p = self.dir / CHAT_FILE
        if not p.exists() and not p.with_name(p.name + ".bak").exists():
            return []
        try:
            return list(read_json(p).get("turns") or [])
        except (OSError, ValueError, AttributeError):
            return []           # a broken chat log must not stop the episode from opening

    def _save_chat(self) -> None:
        try:
            atomic_write_json(self.dir / CHAT_FILE, {"schema": 1, "episode": self.id, "turns": self._chat_log},
                              protected=tuple(Path(m.path) for m in self.media.values()))
        except OSError:
            pass                # the chat answer still goes out; the log catches up on the next turn

    def utterances(self, lo: float, hi: float, enabled: frozenset[str], cuts) -> list[Utterance]:
        """Transcript words still audible on this timeline between lo and hi (timeline seconds),
        grouped per host into utterances u1, u2, ... in time order."""
        if not self.transcript:
            return []
        sr = self.sr
        a_s, b_s = to_base(int(lo * sr), cuts) / sr, to_base(int(hi * sr), cuts, right=False) / sr
        lifts: dict[str, list[tuple[int, int]]] = {}
        slips: dict[str, list[tuple[int, int, int]]] = {}
        for i in enabled:
            for o in self.edits[i].ops:
                if o["op"] == "lift":
                    lifts.setdefault(o["track"], []).append((o["start"], o["end"]))
                elif o["op"] == "slip":
                    slips.setdefault(o["track"], []).append((o["start"], o["end"], o["delta"]))
        starts = [c[0] for c in cuts]

        def gone(track: str, mid: int) -> bool:
            k = bisect.bisect_right(starts, mid) - 1
            if k >= 0 and cuts[k][0] <= mid < cuts[k][1]:
                return True
            return any(x <= mid < y for x, y in lifts.get(track, ()))

        per: dict[str, list[Word]] = {}
        for track, s, e, w in self.words(a_s, b_s):
            mid = int((s + e) / 2 * sr)
            if gone(track, mid):
                continue
            d = next((dl for x, y, dl in slips.get(track, ()) if x <= mid < y), 0)
            ts, te = to_tl(int(s * sr) + d, cuts) / sr, to_tl(int(e * sr) + d, cuts) / sr
            if lo <= ts and te <= hi + 0.5:
                per.setdefault(track, []).append(Word(w, round(ts, 3), round(max(te, ts + 0.01), 3)))
        groups: list[tuple[str, list[Word]]] = []
        for track, ws in per.items():
            cur: list[Word] = []
            for w in ws:
                if cur and (w.start - cur[-1].end > 0.6 or (w.start - cur[-1].end > 0.25 and w.end - cur[0].start > 15)):
                    groups.append((track, cur))
                    cur = []
                cur.append(w)
            if cur:
                groups.append((track, cur))
        groups.sort(key=lambda g: g[1][0].start)
        return [Utterance(f"u{i + 1}", tr, ws) for i, (tr, ws) in enumerate(groups)]

    def removed_text(self, eid: str, limit: int = 60) -> str:
        words = "".join(w["t"] for ln in self.edit_text(eid, ctx_s=0.0) for w in ln["words"] if w["removed"])
        return words[:limit] + ("…" if len(words) > limit else "")

    def _near(self, t: float, radius: float, cuts) -> list[str]:
        out = []
        for e in self.edits.values():
            sp = e.span
            if sp and e.status in (APPLIED, RESTORED) and abs(to_tl(sp[0], cuts) / self.sr - t) <= radius:
                out.append(e.id)
        return sorted(out, key=lambda i: self.edits[i].span[0])

    def _make_proposal(self, p: Proposal, cuts, mix: np.ndarray, lo: float) -> tuple[dict | None, str | None]:
        """(proposal, why not) for the editor's answer on the timeline given by `cuts`."""
        cut_list, restores = p.normalized()
        restores = [r for r in restores if r in self.edits and self.edits[r].status == APPLIED]
        sr = self.sr

        def snap(x):   # nudge the boundary to the quietest nearby sample of the mix
            i = int((x - lo) * sr)
            return int(lo * sr) + snap_cut([mix], i, sr, radius_ms=40) if 0 < i < len(mix) else int(x * sr)

        ops: list[dict] = []
        ripple = sorted((snap(c["start"]), snap(c["end"])) for c in cut_list if not c.get("track"))
        merged: list[list[int]] = []
        for a, b in ripple:                 # overlapping or touching cuts become one
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        for a, b in merged:
            if b - a >= int(0.05 * sr):
                ops += [{"op": "cut", "start": x, "end": y, "tracks": None}
                        for x, y in subtract(to_base(a, cuts, right=True), to_base(b, cuts, right=False), cuts)]
        for c in cut_list:
            if c.get("track"):
                if c["track"] not in {tr.name for tr in self.base.tracks}:
                    continue
                a, b = int(c["start"] * sr), int(c["end"] * sr)
                ops += [{"op": "lift", "track": c["track"], "start": x, "end": y}
                        for x, y in subtract(to_base(a, cuts, right=True), to_base(b, cuts, right=False), cuts)
                        if y - x >= int(0.03 * sr)]
        if not ops and not restores:
            return None, None
        changes: list[dict] = []
        target = None
        if ops:
            e = self.add_edit(ops, p.category, p.title or "聊天修改", p.reason, p.confidence, source="chat")
            changes += [{"id": e.id, "field": "status", "new": APPLIED},
                        {"id": e.id, "field": "approved", "new": True}]
            target = e.id
        for r in restores:
            changes.append({"id": r, "field": "status", "new": RESTORED})
        target = target or restores[0]
        try:
            self.timeline_for(self._enabled_after(changes))
        except ConflictError:
            if ops:
                self.edits[target].status = DISCARDED
            return None, "这个改动和已有的改动冲突，没法应用。"
        for old in [k for k, v in self.proposals.items() if v["state"] == "pending"]:
            self.discard_proposal(old)          # a new instruction supersedes the last one
        self.proposals = {k: v for k, v in self.proposals.items() if v["state"] == "pending"}
        pid = uuid.uuid4().hex[:10]
        self.proposals[pid] = {"id": pid, "title": p.title or "聊天修改", "message": p.message, "target": target,
                               "changes": changes, "state": "pending"}
        self.save()
        return self.proposals[pid], None

    def approve_proposal(self, pid: str) -> None:
        p = self._proposal(pid)
        if p["state"] != "pending":
            raise ConflictError("这个建议已经处理过了")
        self.change(f"批准：{p['title']}", [(c["id"], c["field"], c["new"]) for c in p["changes"]])
        p["state"] = "approved"
        self._turn_state(pid, "approved")
        self.save()

    def discard_proposal(self, pid: str) -> None:
        with self.lock:
            p = self._proposal(pid)
            p["state"] = "discarded"
            self._turn_state(pid, "discarded")
            e = self.edits.get(p["target"])
            if e and e.status == PROPOSED:
                e.status = DISCARDED
            self.save()

    # ------------------------------------------------------------------ persistence
    def state_dict(self) -> dict:
        self.timeline_for(self.enabled)     # never persist an invalid state
        return {"schema": STATE_SCHEMA, "project": self.project_dict(self.enabled),
                "edits": [asdict(e) for e in self.edits.values()],
                "history": self.history, "proposals": self.proposals}

    def save(self) -> None:
        with self.lock:
            atomic_write_json(self.dir / STATE_FILE, self.state_dict(),
                              protected=tuple(Path(m.path) for m in self.media.values()))

    def close(self) -> None:
        if self._pool:
            self._pool.close()

    # ------------------------------------------------------------------ transcript
    def _load_transcript(self) -> dict | None:
        name = self.meta.get("transcript")
        if not name:
            return None
        p = self.dir / Path(name).name
        return read_json(p) if p.is_file() else None

    def words(self, a_s: float, b_s: float) -> list[tuple[str, float, float, str]]:
        if not self.transcript:
            return []
        out = []
        for track, words in self.transcript["tracks"].items():
            out += [(track, s, e, w) for s, e, w in words if e > a_s and s < b_s]
        return sorted(out, key=lambda x: x[1])

    def transcript_text(self, base_s: float, radius: float = 15.0) -> str:
        parts, prev = [], None
        for track, _, _, w in self.words(base_s - radius, base_s + radius):
            if track != prev:
                parts.append(f"\n{track}: ")
                prev = track
            parts.append(w)
        return "".join(parts).strip()

    def edit_text(self, eid: str, ctx_s: float = 6.0) -> list[dict]:
        """Original words around an edit, each marked removed or kept (read-only)."""
        e = self._edit(eid)
        if not e.span:
            return []
        a, b = (x / self.sr for x in e.span)
        removed = [(o["start"] / self.sr, o["end"] / self.sr, o.get("track")) for o in e.ops
                   if o["op"] in ("cut", "lift")]
        lines: list[dict] = []
        for track, s, en, w in self.words(a - ctx_s, b + ctx_s):
            mid = (s + en) / 2
            gone = any(x <= mid < y and (tr is None or tr == track) for x, y, tr in removed)
            if not lines or lines[-1]["speaker"] != track or s - lines[-1]["_end"] > 1.5:
                lines.append({"speaker": track, "words": [], "_end": en})
            lines[-1]["words"].append({"t": w, "removed": gone})
            lines[-1]["_end"] = en
        for ln in lines:
            del ln["_end"]
        return lines

    # ------------------------------------------------------------------ views
    def edit_json(self, e: Edit, cuts) -> dict:
        sp = e.span
        t = to_tl(sp[0], cuts) / self.sr if sp else 0.0
        removed = sum(b - a for a, b in e.cuts) or (sum(o["end"] - o["start"] for o in e.ops if o["op"] == "lift"))
        off = float(self.meta.get("raw_offset_s", 0.0))
        return {
            "id": e.id, "category": e.category, "category_label": CATEGORY_LABELS.get(e.category, e.category),
            "title": e.title, "reason": e.reason, "confidence": e.confidence,
            "consequential": e.consequential, "status": e.status, "approved": e.approved,
            "source": e.source, "t": round(t, 3), "len": round(removed / self.sr, 3),
            "tracks": e.tracks, "op_id": e.op_id, "ai_category": e.ai_category, "speech_s": e.speech_s,
            "raw": [round(sp[0] / self.sr + off, 2), round(sp[1] / self.sr + off, 2)] if sp else None,
        }

    def summary(self) -> dict:
        with self.lock:
            enabled = self.enabled
            tl = self.timeline_for(enabled)
            cuts = self.cuts_for(enabled)
            key = self.version_key(enabled)
            edits = [self.edit_json(e, cuts) for e in self.edits.values() if e.status in (APPLIED, RESTORED)]
            edits.sort(key=lambda d: d["t"])
            routine: dict[str, dict] = {}
            for d in edits:
                if not d["consequential"] and d["source"] == "first_cut":
                    r = routine.setdefault(d["category"], {"category": d["category"], "label": d["category_label"],
                                                           "count": 0, "seconds": 0.0, "restored": 0})
                    r["count"] += 1
                    r["seconds"] = round(r["seconds"] + d["len"], 2)
                    r["restored"] += d["status"] == RESTORED
            tracks = []
            for tr in tl.tracks:
                spans: list[list[float]] = []
                for c in tr.clips:
                    s, en = c.start / self.sr, c.end / self.sr
                    if spans and abs(spans[-1][1] - s) < 1e-6:
                        spans[-1][1] = round(en, 3)
                    else:
                        spans.append([round(s, 3), round(en, 3)])
                tracks.append({"name": tr.name, "gain_db": tr.gain_db, "clips": spans})
            undo, redo = self.history["undo"], self.history["redo"]
            pending_review = sum(1 for d in edits if d["consequential"] and not d["approved"])
            review = [d["id"] for d in sorted((d for d in edits if d["consequential"]), key=review_sort_key)]
            return {
                "id": self.id, "title": self.meta.get("title", self.id), "demo": bool(self.meta.get("demo")),
                "demo_note": self.meta.get("demo_note", ""), "sample_rate": self.sr,
                "duration": round(tl.length / self.sr, 3), "raw_duration": round(self.base.length / self.sr, 3),
                "raw_offset_s": float(self.meta.get("raw_offset_s", 0.0)),
                "version": key, "audio_url": f"/api/episodes/{self.id}/audio/{key}.wav",
                "can_undo": bool(undo), "can_redo": bool(redo),
                "undo_label": undo[-1]["label"] if undo else None,
                "redo_label": redo[-1]["label"] if redo else None,
                "tracks": tracks, "topics": self.meta.get("topics", []),
                "edits": edits, "routine": sorted(routine.values(), key=lambda r: -r["count"]),
                "pending_review": pending_review, "review": review,
                "proposals": [p | {"edit": self.edit_json(self.edits[p["target"]], cuts)}
                              for p in self.proposals.values() if p["state"] == "pending"],
                "has_transcript": self.transcript is not None,
            }

    def map_playhead(self, t_s: float, before: frozenset[str], after: frozenset[str]) -> float:
        base = to_base(int(t_s * self.sr), self.cuts_for(before))
        return round(to_tl(base, self.cuts_for(after)) / self.sr, 3)


def create_episode(ws: Workspace, episode_id: str, meta: dict, project: Project, edits: list[Edit],
                   transcript: dict | None = None) -> Path:
    """Write a new episode folder (used by the demo script and tests). The project must be the
    base (uncut) timeline with an empty log; edits carry the first cut."""
    import json
    d = ws.ensure().episode_dir(episode_id)
    d.mkdir(parents=True, exist_ok=True)
    if transcript is not None:
        meta = {**meta, "transcript": "transcript.json"}
        atomic_write_json(d / "transcript.json", transcript)
    atomic_write_json(d / META_FILE, meta)
    atomic_write_json(d / STATE_FILE, {"schema": STATE_SCHEMA, "project": json.loads(project.to_json()),
                                       "edits": [asdict(e) for e in edits],
                                       "history": {"undo": [], "redo": []}, "proposals": {}})
    ep = Episode(ws, episode_id)   # validate + rewrite with the derived log
    ep.save()
    ep.close()
    return d
