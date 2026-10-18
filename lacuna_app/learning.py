"""Learning from Leon's review (D27, phase 5): his decisions on the AI first cut become candidate rules.

Sources (read-only, from each episode's ``state.json``): every first-cut edit's final status, how it got
there (one decision, a batch sign-off, or never touched) and the chat cuts Leon asked for himself.

* ``decisions(ep)``     -> one `Decision` per edit Leon has a verdict on (kept / restored / accepted /
  declined / added / untouched).
* ``learn(decisions)``  -> candidate rules with counts and examples. A rule only ever *changes* future
  work once Leon approves it (D17: inferred rules need approval): approved rules feed the AI first-cut
  prompt (`prompt_rules`) and which edits go to review (`review_policy`).
* ``Learning``          -> the workspace store: ``<workspace>/learning/rules.json`` (approval state +
  the approved snapshot of each rule) and ``learning/decisions/<episode>.json`` (each episode's verdicts,
  kept so the evidence survives even if an episode folder is deleted).

Rule ids are stable (kind + key), so re-learning after more review updates the evidence of the same
rule. An approved rule stays in force exactly as approved; if new evidence changes its text, the new
version shows as an update for Leon to approve again.
"""
from __future__ import annotations

import bisect
import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .review import REVIEW_CONFIDENCE, ReviewPolicy
from .store import Workspace, atomic_write_json, check_id, read_json
from .i18n import N_, lang, tr

LEARN_DIR = "learning"
RULES_FILE = "rules.json"

APPLIED, RESTORED = "applied", "restored"
SUGGESTION_PREFIX = "AI 建议（未删）"  # i18n-ignore

# verdicts
KEPT, RESTORED_V, ACCEPTED, DECLINED, ADDED, UNTOUCHED = "kept", "restored", "accepted", "declined", "added", "untouched"
# how much a "keep" says about Leon's taste: one considered decision, a batch sign-off, or no action
WEIGHT = {"single": 1.0, "batch": 0.5, "none": 0.25, "hand_edit": 0.5}
# what his own edit of a past episode says weighs half a review decision either way (it predates the
# rules he stated since). Where it contradicts an explicit rule, the explicit rule wins (precedence in
# EDITORIAL_RULES.md): R002 asks for Pei's stumbles to be cut more than EP001 showed, so his old edit
# keeping them is not evidence against cutting them.
EXPLICIT_OVERRIDES = {("disfluency", "Pei"), ("repetition", "Pei")}

KIND_LABELS = {
    "pause": N_("停顿收紧"), "disfluency": N_("口误"), "repetition": N_("重复"), "crosstalk": N_("抢话"),
    "content": N_("内容删减"), "interjection_move": N_("插话挪位"), "single_track_noise": N_("单轨杂声"),
    "filler": N_("口误与重复"), "interjection": N_("插话处理"), "single_track": N_("单轨删减"), "chat": N_("聊天修改"),
}
HOST_LABELS = {"Leon": "Leon", "Pei": "Pei", "both": N_("两人"), "none": N_("无人说话处")}

# evidence needed before a pattern becomes a candidate rule
MIN_RESTORED = 3          # "AI cuts too much of X": at least this many restores ...
PROTECT_RATE = 0.3        # ... and at least this share of the (weighted) decisions on X
MIN_TRUSTED = 8           # "X never needs review": this much (weighted) considered agreement ...
TRUST_RATE = 0.1          # ... at most this weighted restore rate, and no restore in review
REVIEW_RATE = 0.15        # a routine kind restored this often goes to review
MIN_ADDED = 2             # "AI misses X": Leon had to ask for X this many times
MIN_ACCEPTED = 3          # "AI too timid on X": suggestions Leon applied ...
ACCEPT_RATE = 0.6         # ... as a share of the suggestions he decided on
MIN_TASTE = 3             # content verdicts needed before they are worth showing the editor
MAX_EXAMPLES = 6
TASTE_EXAMPLES = 8        # per side, longest first
MISSED_SPEECH_S = 3.0     # speech he cut himself (AI untouched) worth showing as a missed example
CONF_BUCKETS = (0.4, 0.5, 0.6, 0.7)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ============================================================================ decisions

@dataclass
class Decision:
    episode: str
    edit_id: str
    source: str              # first_cut / chat / manual
    kind: str                # AI category when known (disfluency, content ...), else app category
    category: str            # app category (content / filler / pause ...)
    host: str                # whose speech the edit removes: Leon / Pei / both / none
    verdict: str             # kept / restored / accepted / declined / added / untouched
    how: str                 # single / batch / none (review) or hand_edit
    confidence: float
    length_s: float
    speech_s: float
    text: str                # words the edit removes (or would remove)
    reason: str
    raw: list[float] | None  # raw recording seconds
    consequential: bool = False


def _last_touch(history: dict) -> dict[str, str]:
    """edit id -> label of the last undo-stack step that changed it (redo entries were undone)."""
    out: dict[str, str] = {}
    for entry in history.get("undo", []):
        for c in entry["changes"]:
            out[c["id"]] = entry["label"]
    return out


def _first_status(history: dict) -> dict[str, str]:
    """edit id -> its status before Leon first changed it."""
    out: dict[str, str] = {}
    for entry in history.get("undo", []) + list(reversed(history.get("redo", []))):
        for c in entry["changes"]:
            if c["field"] == "status":
                out.setdefault(c["id"], c["old"])
    return out


def _host(ep, e) -> tuple[str, float, float]:
    """(host, Leon speech s, Pei speech s) removed by edit `e` (lifts: their track)."""
    per: dict[str, float] = defaultdict(float)
    sr = ep.sr
    ranges = [(o["start"] / sr, o["end"] / sr, o.get("track")) for o in e.ops if o["op"] in ("cut", "lift", "erase")]
    for a, b, track in ranges:
        for trk, s, en, _w in ep.words(a, b):
            if track is None or trk == track:
                per[trk] += max(0.0, min(b, en) - max(a, s))
    lift_tracks = {o["track"] for o in e.ops if o["op"] in ("lift", "erase", "slip")}
    if lift_tracks and not e.cuts:
        return (lift_tracks.pop() if len(lift_tracks) == 1 else "both"), per["Leon"], per["Pei"]
    top = max(per.values(), default=0.0)
    if top < 0.05:
        return "none", per["Leon"], per["Pei"]
    big = [t for t, v in per.items() if v >= 0.3 * top]
    return (big[0] if len(big) == 1 else "both"), per["Leon"], per["Pei"]


def _text(ep, e, host: str, limit: int = 40) -> str:
    """The words edit `e` removes, per track (no interleaving of the two hosts)."""
    sr = ep.sr
    ranges = [(o["start"] / sr, o["end"] / sr, o.get("track")) for o in e.ops if o["op"] in ("cut", "lift", "erase")]
    per: dict[str, list[str]] = defaultdict(list)
    for a, b, track in ranges:
        for trk, s, en, w in ep.words(a, b):
            if (track is None or trk == track) and a <= (s + en) / 2 < b:
                per[trk].append(w)
    order = [host] if host in per else sorted(per, key=lambda t: -len(per[t]))
    txt = " / ".join("".join(per[t]) for t in order if per[t])
    return txt[:limit] + ("…" if len(txt) > limit else "")


def decisions(ep, accepted_as_is: bool = False) -> list[Decision]:
    """Leon's verdict on every edit of an open `Episode` (read-only). `accepted_as_is`: Leon said his
    clicks in this episode were only trying the app; count the AI first cut as he received it as
    signed off (a batch keep of every cut, suggestions left uncut), and ignore the clicks."""
    if accepted_as_is:
        return _as_received(ep)
    with ep.lock:
        last = _last_touch(ep.history)
        first = _first_status(ep.history)
        out: list[Decision] = []
        for e in ep.edits.values():
            if e.status not in (APPLIED, RESTORED) or e.source == "level":
                continue                               # chat proposals never approved; volume is not an edit verdict
            label = last.get(e.id, "")
            how = "none" if not label else ("batch" if label.startswith("全部") else "single")  # i18n-ignore
            if e.source == "first_cut":
                initial = first.get(e.id, RESTORED if e.title.startswith(SUGGESTION_PREFIX) else e.status)
                if initial == APPLIED:
                    verdict = KEPT if e.status == APPLIED else RESTORED_V
                else:
                    verdict = ACCEPTED if e.status == APPLIED else DECLINED
                if verdict in (KEPT, DECLINED) and not e.approved and how != "batch":
                    verdict, how = UNTOUCHED, "none"
            else:
                if e.status != APPLIED:
                    continue                           # Leon's own cut, later undone: no signal
                verdict, how = ADDED, "single"
            host, _, _ = _host(ep, e)
            j = ep.edit_json(e, [])
            out.append(Decision(
                episode=ep.id, edit_id=e.id, source=e.source, kind=e.ai_category or e.category,
                category=e.category, host=host, verdict=verdict, how=how, confidence=float(e.confidence),
                length_s=j["len"], speech_s=float(e.speech_s), text=_text(ep, e, host),
                reason=(e.reason or "")[:120], raw=j["raw"], consequential=e.consequential))
        return out


# ============================================================================ rules

@dataclass
class Rule:
    id: str
    kind: str                # protect / review / trust / missed / timid / taste / threshold / ask (chat)
    title: str               # one line for Leon
    detail: str              # the evidence, in words
    prompt: str              # what the AI first-cut editor is told once approved
    key: dict                # {category, host} or {confidence}
    evidence: dict           # counts behind it
    examples: list[dict] = field(default_factory=list)   # {text, raw, verdict, episode}
    policy: dict | None = None   # effect on the review queue once approved

    def digest(self) -> str:
        """Fingerprint of what approving this rule would change (title/prompt/policy, not counts)."""
        s = json.dumps([self.title, self.prompt, self.policy], ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(s.encode()).hexdigest()[:12]


def _rid(kind: str, *parts: str) -> str:
    return f"{kind}:" + ":".join(parts)


def _what(kind: str, host: str) -> str:
    k = tr(KIND_LABELS.get(kind, kind))
    if lang() == "en":
        k = k[:1].lower() + k[1:]                   # inside a sentence ("Leon's stumbles")
    return tr("{host}的{kind}", host=tr(HOST_LABELS.get(host, host)), kind=k) if host in ("Leon", "Pei") else k


def _en(host: str) -> str:
    return {"Leon": "Leon's speech", "Pei": "Pei's speech", "both": "both hosts' speech"}.get(host, "silences")


def _example(d: Decision) -> dict:
    return {"text": d.text, "raw": d.raw, "verdict": d.verdict, "episode": d.episode, "reason": d.reason}


def _quote(ds: Iterable[Decision], n: int = 4) -> str:
    qs = [f"「{d.text}」" for d in ds if d.text][:n]
    return "、".join(qs)


def _prompt_quotes(ds: Iterable[Decision], n: int = 4) -> str:
    return "; ".join(f'"{d.text}" (raw {d.raw[0]:.0f}s)' if d.raw else f'"{d.text}"' for d in ds if d.text)[:400]


def _merge(ds: list[Decision]) -> list[Decision]:
    """A considered review decision on an edit replaces what the hand edit says about the same edit."""
    reviewed = {(d.episode, d.edit_id) for d in ds if d.how == "single"}
    return [d for d in ds if not (d.how == "hand_edit" and (d.episode.split(".")[0], d.edit_id) in reviewed)]


def _w(d: Decision) -> float:
    if d.verdict in (RESTORED_V, ACCEPTED, DECLINED, ADDED):
        return 0.5 if d.how == "hand_edit" else 1.0
    return WEIGHT[d.how]


def _sources(ds: list[Decision], review_word: str, hand_word: str) -> str:
    r = sum(d.how != "hand_edit" for d in ds)
    h = len(ds) - r
    parts = ([tr("审阅里{review_word} {r} 处", review_word=review_word, r=r)] if r else []) + ([tr("你手剪的成品里{hand_word} {h} 处", hand_word=hand_word, h=h)] if h else [])
    return (", " if lang() == "en" else "，").join(parts)


def learn(ds: list[Decision]) -> list[Rule]:
    """Candidate rules from Leon's decisions (all episodes, both sources). Pure: same input, same rules."""
    ds = _merge(ds)
    rules: list[Rule] = []
    first = [d for d in ds if d.source == "first_cut"]
    cut = [d for d in first if d.verdict in (KEPT, RESTORED_V, UNTOUCHED)]          # AI did cut
    groups: dict[tuple[str, str], list[Decision]] = defaultdict(list)
    for d in cut:
        groups[(d.kind, d.host)].append(d)

    for (kind, host), g in sorted(groups.items()):
        restored = [d for d in g if d.verdict == RESTORED_V
                    and not (d.how == "hand_edit" and (kind, host) in EXPLICIT_OVERRIDES)]
        kept = [d for d in g if d.verdict in (KEPT, UNTOUCHED)]
        r_w, k_w = sum(_w(d) for d in restored), sum(_w(d) for d in kept)
        rate = r_w / (r_w + k_w) if r_w + k_w else 0.0
        considered = [d for d in kept if d.verdict == KEPT and d.how in ("single", "hand_edit")]
        what = _what(kind, host)
        n_edits = len({(d.episode.split(".")[0], d.edit_id) for d in g})
        ev = {"ai_cut": n_edits, "restored": len(restored),
              "restored_review": sum(d.how != "hand_edit" for d in restored),
              "kept": sum(d.verdict == KEPT for d in g), "kept_single": sum(d.how == "single" for d in considered),
              "untouched": sum(d.verdict == UNTOUCHED for d in g), "restore_rate": round(rate, 2)}
        key = {"category": kind, "host": host}
        routine = not any(d.consequential for d in g)
        ex = [_example(d) for d in restored[:MAX_EXAMPLES]]
        if len(restored) >= MIN_RESTORED and rate >= PROTECT_RATE:
            rules.append(Rule(
                _rid("protect", kind, host), "protect",
                tr("{what}：AI 删多了，以后少删", what=what),
                tr("AI 删了 {n_edits} 处{what}，其中{p2}（加权约 {rate}）。例如 {p4}。", n_edits=n_edits, what=what, p2=_sources(restored, tr('恢复了'), tr('没删')), rate=f"{rate:.0%}", p4=_quote(restored)),
                (f"Leon undid {len(restored)} of {n_edits} pause tightenings ({rate:.0%} weighted): leave more air; "
                 f"tighten only clearly dead gaps." if kind == "pause" else
                 f"Leon kept the words in {len(restored)} of {n_edits} '{kind}' cuts on {_en(host)} ({rate:.0%} "
                 f"weighted): cut this kind there much less often; only clear, distracting cases. Examples he kept: "
                 f"{_prompt_quotes(restored)}."),
                key, ev, ex, {"review": True} if routine else None))
        elif routine and len(restored) >= MIN_RESTORED and rate >= REVIEW_RATE and ev["restored_review"]:
            rules.append(Rule(
                _rid("review", kind, host), "review",
                tr("{what}：以后放进审阅让你过目", what=what),
                tr("这类原来算常规清理、自动应用，但{p0}（加权约 {rate}），不该不问你就删。例如 {p2}。", p0=_sources(restored, tr('恢复了'), tr('没删')), rate=f"{rate:.0%}", p2=_quote(restored)),
                "", key, ev, ex, {"review": True}))
        if (not routine and not ev["restored_review"] and rate <= TRUST_RATE
                and sum(_w(d) for d in considered) >= MIN_TRUSTED):
            rules.append(Rule(
                _rid("trust", kind, host), "trust",
                tr("{what}：AI 删得对，以后不用逐条过目", what=what),
                tr("{p0}{what}，审阅里一处没恢复。以后这类直接应用（仍可在列表里恢复），删掉超过 5 秒说话的仍会让你过目。", p0=_sources(considered, tr('确认了'), tr('也删了')), what=what),
                f"Leon agreed with {len(considered)} '{kind}' cuts on {host}'s speech: keep cutting this kind "
                f"at the same rate.",
                key, ev, [_example(d) for d in considered[:MAX_EXAMPLES]], {"review": False}))

    # suggestions the AI left uncut that Leon cut (in review or in his own edit)
    sugg: dict[tuple[str, str], list[Decision]] = defaultdict(list)
    for d in first:
        if d.verdict in (ACCEPTED, DECLINED):
            sugg[(d.kind, d.host)].append(d)
    for (kind, host), g in sorted(sugg.items()):
        acc = [d for d in g if d.verdict == ACCEPTED]
        rate = len(acc) / len(g)
        if len(acc) >= MIN_ACCEPTED and rate >= ACCEPT_RATE:
            what = _what(kind, host)
            rules.append(Rule(
                _rid("timid", kind, host), "timid",
                tr("{what}：AI 太犹豫，该直接删", what=what),
                tr("AI 没敢删、留给你决定的 {p0} 处{what}里，{p2}。例如 {p3}。", p0=len(g), what=what, p2=_sources(acc, tr('你删了'), tr('删了')), p3=_quote(acc)),
                f"When unsure about '{kind}' on {_en(host)}, cut it (Leon cut {len(acc)} of {len(g)} such "
                f"suggestions): {_prompt_quotes(acc)}.",
                {"category": kind, "host": host}, {"suggested": len(g), "accepted": len(acc)},
                [_example(d) for d in acc[:MAX_EXAMPLES]]))

    # cuts Leon had to ask for in chat
    added: dict[tuple[str, str], list[Decision]] = defaultdict(list)
    for d in ds:
        if d.verdict == ADDED and d.how != "hand_edit":
            added[(d.kind, d.host)].append(d)
    for (kind, host), g in sorted(added.items()):
        if len(g) >= MIN_ADDED:
            what = _what(kind, host) if kind != "chat" else tr("{p0}说的话", p0=tr(HOST_LABELS.get(host, host)))
            rules.append(Rule(
                _rid("missed", kind, host), "missed",
                tr("{what}：AI 漏删了，你得自己说", what=what),
                tr("你在聊天里让 AI 补删了 {p0} 处{what}。例如 {p2}。", p0=len(g), what=what, p2=_quote(g)),
                f"Leon had to ask for {len(g)} extra cuts of this kind ({kind}) on {_en(host)} after the first "
                f"cut; look for similar passages: {_prompt_quotes(g)}.",
                {"category": kind, "host": host}, {"added": len(g)}, [_example(d) for d in g[:MAX_EXAMPLES]]))

    # content taste: which passages he cut and which he kept, per host - the part rules cannot capture
    for host in ("Leon", "Pei", "both"):
        g = [d for d in ds if d.kind == "content" and d.host == host and
             (d.verdict in (RESTORED_V, ACCEPTED, DECLINED, ADDED) or (d.verdict == KEPT and d.how != "batch"))]
        cut_ = sorted([d for d in g if d.verdict in (KEPT, ACCEPTED, ADDED)], key=lambda d: -d.speech_s)
        kept = sorted([d for d in g if d.verdict in (RESTORED_V, DECLINED)], key=lambda d: -d.speech_s)
        if len(g) < MIN_TASTE or not cut_ or not kept:
            continue          # all one way: the protect / trust / timid rules already say it
        who = tr(HOST_LABELS[host])
        missed = [d for d in cut_ if d.verdict == ADDED]
        rules.append(Rule(
            _rid("taste", "content", host), "taste",
            tr("{who}的内容删减：按你删 / 留的例子学品味", who=who),
            tr("跑题和啰嗦段落你删了 {p0} 处（如 {p1}），留了 {p2} 处（如 {p3}）", p0=len(cut_), p1=_quote(cut_, 3), p2=len(kept), p3=_quote(kept, 3)) + (tr("；其中 {p0} 处是 AI 没删、你手剪时删掉的", p0=len(missed)) if missed else "")
            + tr("。这些例子会给 AI 参考，让它挑段落时更像你。"),
            f"Leon's taste on content trims of {_en(host)} (learn the kind of passage, not the ranges). "
            f"He CUT: {_prompt_quotes(cut_[:TASTE_EXAMPLES])}. "
            f"He KEPT (do not cut passages like these): {_prompt_quotes(kept[:TASTE_EXAMPLES])}.",
            {"category": "content", "host": host}, {"cut": len(cut_), "kept": len(kept), "missed_by_ai": len(missed)},
            [_example(d) for d in (cut_[:3] + kept[:3])]))

    # confidence: is the AI's confidence worth a threshold?  (review decisions only: it is about review)
    routine_cut = [d for d in cut if not d.consequential and d.kind != "pause" and d.how != "hand_edit"]
    if routine_cut:
        buckets = []
        lo = 0.0
        for hi in CONF_BUCKETS + (1.01,):
            b = [d for d in routine_cut if lo <= d.confidence < hi]
            r = sum(d.verdict == RESTORED_V for d in b)
            w = r + sum(WEIGHT[d.how] for d in b if d.verdict != RESTORED_V)
            buckets.append((lo, hi, len(b), r, r / w if w else 0.0))
            lo = hi
        # the highest threshold below which every populated bucket is restored >= REVIEW_RATE
        thr = 0.0
        for blo, bhi, n, r, rate in buckets:
            if n == 0:
                continue
            if n >= 5 and r >= 2 and rate >= REVIEW_RATE:
                thr = min(bhi, 1.0)
            else:
                break
        if thr > REVIEW_CONFIDENCE:
            rules.append(Rule(
                _rid("threshold", "confidence"), "threshold",
                tr("AI 把握度低于 {thr} 的常规删除也让你过目", thr=f"{thr:.1f}"),
                tr("按把握度分组，你恢复的比例：")
                + (", " if lang() == "en" else "，").join(tr("{a}–{p1} 恢复 {r}/{n}", a=f"{a:.1f}", p1=f"{min(b, 1):.1f}", r=r, n=n) for a, b, n, r, _ in buckets if n)
                + tr("。低于 {thr} 时恢复率偏高，这些不该自动应用。", thr=f"{thr:.1f}"),
                "", {"confidence": thr},
                {"buckets": [{"lo": a, "hi": min(b, 1.0), "n": n, "restored": r, "rate": round(x, 2)}
                             for a, b, n, r, x in buckets]},
                policy={"confidence": thr}))
    return rules


# ============================================================================ second source: Leon's own hand edit

def _spans_overlap(spans: list[tuple[float, float]], a: float, b: float) -> float:
    i = bisect.bisect_right([s for s, _ in spans], b)
    return sum(max(0.0, min(b, y) - max(a, x)) for x, y in spans[max(0, i - 64):i])


def _as_received(ep) -> list[Decision]:
    with ep.lock:
        first = _first_status(ep.history)
        out: list[Decision] = []
        for e in ep.edits.values():
            if e.source != "first_cut":
                continue
            initial = first.get(e.id, RESTORED if e.title.startswith(SUGGESTION_PREFIX) else e.status)
            if initial not in (APPLIED, RESTORED):
                continue
            host, _, _ = _host(ep, e)
            j = ep.edit_json(e, [])
            out.append(Decision(
                episode=ep.id, edit_id=e.id, source=e.source, kind=e.ai_category or e.category, category=e.category,
                host=host, verdict=KEPT if initial == APPLIED else DECLINED, how="batch",
                confidence=float(e.confidence), length_s=j["len"], speech_s=float(e.speech_s),
                text=_text(ep, e, host), reason=(e.reason or "")[:120], raw=j["raw"],
                consequential=e.consequential))
        return out


def hand_edit_decisions(ep, removed: dict[str, list], ambiguous: dict[str, list] | None = None,
                        tol: float = 0.1) -> list[Decision]:
    """Label the episode's first-cut edits with what Leon did in his OWN edit of the same recording
    (D29: the S4 alignment of his finished episode). `removed` / `ambiguous`: track name -> raw-second
    spans he removed / that the alignment cannot decide. Also returns the speech he cut that the AI left
    in (verdict "added"). Read-only; the result is a decision snapshot like the review's."""
    off = float(ep.meta.get("raw_offset_s", 0.0))
    sr = ep.sr
    rem = {t: sorted((a - off - tol, b - off + tol) for a, b in s) for t, s in removed.items()}
    amb = {t: sorted((a - off, b - off) for a, b in s) for t, s in (ambiguous or {}).items()}
    out: list[Decision] = []
    covered: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for e in ep.edits.values():
        if e.source != "first_cut" or not e.span:
            continue
        ranges = [(o["start"] / sr, o["end"] / sr, o.get("track")) for o in e.ops if o["op"] in ("cut", "lift", "erase")]
        if not ranges or e.category == "pause":
            for a, b, track in ranges:
                for trk in ([track] if track else list(rem)):
                    covered[trk].append((a, b))
            continue                                     # slips: nothing removed; pauses: see below
        speech = hit = unsure = 0.0
        for a, b, track in ranges:
            for trk in ([track] if track else list(rem)):
                covered[trk].append((a, b))
            for trk, s, en, _w in ep.words(a, b):
                if track and trk != track:
                    continue
                x, y = max(a, s), min(b, en)
                if y <= x:
                    continue
                speech += y - x
                hit += min(y - x, _spans_overlap(rem.get(trk, []), x, y))
                unsure += min(y - x, _spans_overlap(amb.get(trk, []), x, y))
        if speech < 0.05 or unsure > 0.5 * speech:
            continue        # pauses: his pause lengths are already calibrated as numbers (S5), not per edit
        frac = hit / speech
        if 0.2 < frac < 0.6:
            continue                                     # partly: the alignment cannot tell what he meant
        suggestion = e.title.startswith(SUGGESTION_PREFIX)
        did_cut = frac >= 0.6
        verdict = (ACCEPTED if did_cut else DECLINED) if suggestion else (KEPT if did_cut else RESTORED_V)
        host, _, _ = _host(ep, e)
        j = ep.edit_json(e, [])
        out.append(Decision(
            episode=f"{ep.id}.hand_edit", edit_id=e.id, source="first_cut", kind=e.ai_category or e.category,
            category=e.category, host=host, verdict=verdict, how="hand_edit", confidence=float(e.confidence),
            length_s=j["len"], speech_s=float(e.speech_s), text=_text(ep, e, host),
            reason=(e.reason or "")[:120], raw=j["raw"], consequential=e.consequential))
    # long stretches of speech he cut himself and the AI did not touch: what the AI missed
    for trk, spans in removed.items():
        cov = sorted(covered.get(trk, []))
        for a, b in spans:
            a, b = a - off, b - off
            if b <= 0 or _spans_overlap(cov, a, b) > 0.2 * (b - a):
                continue
            ws = [(s, en, w) for t, s, en, w in ep.words(a, b) if t == trk and s >= a - tol and en <= b + tol]
            sp = sum(en - s for s, en, _ in ws)
            if sp < MISSED_SPEECH_S:
                continue
            out.append(Decision(
                episode=f"{ep.id}.hand_edit", edit_id=f"h{trk[0]}{int(a * 10):06d}", source="hand_edit",
                kind="content", category="content", host=trk, verdict=ADDED, how="hand_edit", confidence=1.0,
                length_s=round(b - a, 2), speech_s=round(sp, 2), text="".join(w for _, _, w in ws)[:40],
                reason="", raw=[round(a + off, 2), round(b + off, 2)], consequential=True))
    return out


# ============================================================================ workspace store

class Learning:
    def __init__(self, ws: Workspace):
        self.ws = ws
        self.dir = ws.root / LEARN_DIR
        self.path = self.dir / RULES_FILE

    # ---- persistence
    def _state(self) -> dict:
        if not self.path.is_file():
            return {"schema": 1, "rules": {}}
        return read_json(self.path)

    def _save(self, st: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.path, st)

    def save_decisions(self, episode_id: str, ds: list[Decision]) -> None:
        d = self.dir / "decisions"
        d.mkdir(parents=True, exist_ok=True)
        atomic_write_json(d / f"{check_id(episode_id)}.json",
                          {"episode": episode_id, "at": _now(), "decisions": [asdict(x) for x in ds]})

    def all_decisions(self) -> list[Decision]:
        d = self.dir / "decisions"
        out: list[Decision] = []
        if d.is_dir():
            for p in sorted(d.glob("*.json")):
                try:
                    out += [Decision(**x) for x in read_json(p)["decisions"]]
                except (OSError, ValueError, KeyError, TypeError):
                    continue        # one unreadable snapshot must not hide the rest
        return out

    # ---- views
    def overview(self, episodes: Iterable = ()) -> dict:
        """Refresh decisions from the open `episodes`, re-learn, merge with approval state."""
        for ep in episodes:
            if ep.meta.get("demo"):
                continue                 # demo data is not Leon's taste
            ds = decisions(ep, accepted_as_is=ep.id in self._state().get("accepted_as_is", []))
            try:
                self.save_decisions(ep.id, ds)
            except OSError:
                pass                     # another request is writing the same snapshot; it is the same data
        ds = self.all_decisions()
        st = self._state()
        rules = []
        from .chat_learning import ChatAsks      # it builds on Rule, so imported here
        for r in learn(ds) + ChatAsks(self.ws).rules():
            s = st["rules"].get(r.id, {})
            state = s.get("state", "candidate")
            if state == "deleted":
                continue                     # Leon deleted it: never shown again, even if re-learned
            approved = s.get("approved")
            changed = state == "approved" and approved and approved.get("digest") != r.digest()
            rules.append(asdict(r) | {"state": state, "updated": bool(changed),
                                      "approved_at": approved.get("at") if approved else None})
        live = {r["id"] for r in rules}
        # approved rules whose evidence no longer produces them stay in force until Leon drops them
        for rid, s in st["rules"].items():
            if rid not in live and s.get("state") == "approved" and s.get("approved"):
                rules.append(s["approved"]["rule"] | {"state": "approved", "updated": False, "stale": True,
                                                      "approved_at": s["approved"].get("at")})
        order = {"candidate": 0, "approved": 1, "rejected": 2}
        rules.sort(key=lambda r: (order.get(r["state"], 3) - (1 if r.get("updated") else 0), r["id"]))
        return {"rules": rules, "stats": stats(ds),
                "pending": sum(r["state"] == "candidate" or bool(r.get("updated")) for r in rules)}

    def decide(self, rule_id: str, action: str, episodes: Iterable = ()) -> dict:
        """approve / reject / reset / delete one rule. Approving freezes the rule as it reads now;
        deleting (only offered for rejected rules) hides it for good, however often it is re-learned."""
        if action not in ("approve", "reject", "reset", "delete"):
            raise ValueError(f"unknown action {action}")
        ov = self.overview(episodes)
        rule = next((r for r in ov["rules"] if r["id"] == rule_id), None)
        if rule is None:
            raise KeyError(rule_id)
        st = self._state()
        if action == "reset":
            st["rules"].pop(rule_id, None)
        elif action == "reject":
            st["rules"][rule_id] = {"state": "rejected", "at": _now()}
        elif action == "delete":
            st["rules"][rule_id] = {"state": "deleted", "at": _now()}
        else:
            core = {k: rule[k] for k in Rule.__dataclass_fields__}
            st["rules"][rule_id] = {"state": "approved", "at": _now(),
                                    "approved": {"at": _now(), "digest": Rule(**core).digest(), "rule": core}}
        self._save(st)
        return self.overview()

    def accept_as_is(self, episode_id: str, on: bool = True) -> None:
        """Count this episode's first cut as accepted as delivered; its review clicks were tests."""
        st = self._state()
        eps = set(st.get("accepted_as_is", []))
        (eps.add if on else eps.discard)(check_id(episode_id))
        st["accepted_as_is"] = sorted(eps)
        self._save(st)

    def active(self) -> list[dict]:
        """Approved rules exactly as Leon approved them."""
        return [s["approved"]["rule"] for s in self._state()["rules"].values()
                if s.get("state") == "approved" and s.get("approved")]


def stats(ds: list[Decision]) -> dict:
    """Headline numbers for the learning page."""
    by: dict[str, int] = defaultdict(int)
    for d in ds:
        by[d.verdict] += 1
    eps = sorted({d.episode for d in ds})
    considered = sum(1 for d in ds if d.how == "single")
    return {"episodes": eps, "decisions": len(ds), "considered": considered, **{k: by[k] for k in
            (KEPT, RESTORED_V, ACCEPTED, DECLINED, ADDED, UNTOUCHED)}}


# ============================================================================ consumers

def prompt_rules(ws: Workspace | str | Path) -> str:
    """Approved learned rules as a block for the AI first-cut prompt ("" if none)."""
    ws = ws if isinstance(ws, Workspace) else Workspace(ws)
    lines = [r["prompt"] for r in Learning(ws).active() if r.get("prompt")]
    if not lines:
        return ""
    return ("LEARNED FROM LEON'S REVIEWS AND CHAT (approved by Leon; these override the generic brief where they "
            "conflict):\n" + "\n".join(f"- {x}" for x in lines))


def review_policy(ws: Workspace | str | Path) -> ReviewPolicy | None:
    """Which edits go to review, as calibrated by the approved rules (None = defaults)."""
    ws = ws if isinstance(ws, Workspace) else Workspace(ws)
    active = Learning(ws).active()
    pol = ReviewPolicy()
    touched = False
    for r in active:
        p = r.get("policy") or {}
        if "review" in p:
            pol.by_kind[(r["key"]["category"], r["key"]["host"])] = bool(p["review"])
            touched = True
        if "confidence" in p:
            pol.confidence = max(pol.confidence, float(p["confidence"]))
            touched = True
    return pol if touched else None


__all__ = ["Decision", "Rule", "Learning", "decisions", "learn", "prompt_rules", "review_policy", "stats",
           "REVIEW_CONFIDENCE"]
