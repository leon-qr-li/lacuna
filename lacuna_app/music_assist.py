"""Help with music placement (docs/decisions/2026-10-17-music-suggestions.md): place by use, and change music by talking.

* `auto_place`: from the library's uses (D48) puts the intro and outro in, and suggests an
  interlude at a break between topics (publish-pack chapter starts first, then the longest pauses
  in the conversation). Everything comes back as a *suggestion* (`EpisodeMusic.set_draft`), heard
  before it is accepted; nothing reaches the export until Leon accepts it.
* `MusicChat`: Leon says "间奏晚两秒" / "背景音小 3 dB" / "片尾去掉"; Claude (text only: the
  placements, library names and notes, chapter headings and nearby transcript) answers with actions
  that are turned into a suggestion the same way.

Times Claude sees and gives are final-mix seconds (what Leon hears); positions are snapped to the
nearest pause so music never starts in the middle of a word.
"""
from __future__ import annotations

import copy
import json
import time
import uuid
from typing import Any

from .episode import ConflictError, to_tl
from .library import KINDS, ROLE_FOR_KIND, credit_line
from .music import ANCHORED, APPLIED, ROLES, TUNING, EpisodeMusic, upgrade_v1
from .i18n import AI_NAME_RULE, N_, in_reply_language, join_list, lang, tr

MIN_BREAK_S = 0.6          # a pause this long between utterances can take an interlude
SNAP_WINDOW_S = 4.0
BREAK_RANGE = (0.2, 0.9)   # interludes go between 20 % and 90 % of the episode
NEAR_S = 25.0              # transcript sent to Claude around each placement


def _mmss(s: float) -> str:
    s = max(0, int(round(s)))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _utterances(m: EpisodeMusic):
    ep = m.ep
    with ep.lock:
        enabled = ep.enabled
        cuts = ep.cuts_for(enabled)
        dur = ep.timeline_for(enabled).length / ep.sr
        return ep.utterances(0.0, dur, enabled, cuts), dur


def pauses(m: EpisodeMusic) -> list[tuple[float, float]]:
    """(midpoint, length) of every pause between utterances (both hosts silent), voice seconds."""
    utts, _ = _utterances(m)
    out = []
    end = None
    for u in sorted(utts, key=lambda u: u.start):
        if end is not None and u.start - end >= 0.3:
            out.append(((end + u.start) / 2, u.start - end))
        end = u.end if end is None else max(end, u.end)
    return out


def snap(m: EpisodeMusic, voice_s: float, window: float = SNAP_WINDOW_S) -> float:
    """The nearest pause to `voice_s` (within `window`), else `voice_s` unchanged."""
    near = [(abs(t - voice_s), t) for t, n in pauses(m) if abs(t - voice_s) <= window]
    return round(min(near)[1], 3) if near else voice_s


def chapter_starts(m: EpisodeMusic) -> list[float]:
    """Voice seconds where the publish pack's sections start (empty without a pack)."""
    try:
        from .publish import Publisher
        pack = Publisher(m.ws).load(m.ep)
    except Exception:    # noqa: BLE001 - chapters are only a hint
        return []
    if not pack:
        return []
    ep = m.ep
    with ep.lock:
        cuts = ep.cuts_for(ep.enabled)
    out = []
    for sec in pack.get("draft", {}).get("sections", [])[1:]:
        if sec.get("entries"):
            out.append(to_tl(int(sec["entries"][0]["base_s"] * ep.sr), cuts) / ep.sr)
    return out


def break_candidates(m: EpisodeMusic, n: int = 4) -> list[float]:
    """Good places for an interlude, best first (voice seconds): pauses at a chapter start, then
    the longest pauses, inside the middle of the episode and at least a minute apart."""
    ps = pauses(m)
    _, dur = _utterances(m)
    if not dur:
        return []
    lo, hi = BREAK_RANGE[0] * dur, BREAK_RANGE[1] * dur
    chapters = chapter_starts(m)

    def score(item):
        t, length = item
        at_chapter = any(abs(t - c) < 8.0 for c in chapters)
        return (at_chapter, length >= MIN_BREAK_S, length)

    picked: list[float] = []
    for t, length in sorted((x for x in ps if lo <= x[0] <= hi), key=score, reverse=True):
        if all(abs(t - q) >= 60.0 for q in picked):
            picked.append(round(t, 3))
        if len(picked) >= n:
            break
    if not picked:
        picked = [round(dur / 2, 3)]
    return picked


def _new(asset_id: str, role: str, source: str) -> dict:
    return {"id": "mu_" + uuid.uuid4().hex[:8], "asset_id": asset_id, "role": role, "at_base": None,
            "until_base": None, **{k: None for k in TUNING}, "gain_db": 0.0, "status": APPLIED, "source": source}


def auto_place(m: EpisodeMusic) -> dict:
    """Suggest music from the library's uses. Returns {"draft": draft or None, "message"}."""
    current = [p for p in m.placements() if p.get("status", APPLIED) == APPLIED]
    have = {p["role"] for p in current}
    assets = sorted(m.lib.assets(), key=lambda a: a.get("added_at") or "", reverse=True)
    rule = m.lib.series_rule(m.load().get("series"))
    ps = copy.deepcopy(current)
    changes, alternatives, left = [], {}, []

    def pick(kind: str) -> dict | None:
        if kind in ("intro", "outro") and (rule or {}).get(kind):
            a = next((x for x in assets if x["id"] == rule[kind]["asset_id"]), None)
            if a:
                return a
        return next((a for a in assets if a.get("kind") == kind), None)

    for role in ("intro", "outro"):
        a = pick(role)
        if role in have or a is None:
            continue
        p = _new(a["id"], role, "auto")
        t = (rule or {}).get(role) or {}
        t = t if t.get("asset_id") == a["id"] else None
        if t:
            t = upgrade_v1(dict(t, role=role), a)
            p.update({k: t.get(k) for k in TUNING}, gain_db=t.get("gain_db") or 0.0)
        ps.append(p)
        changes.append({"pid": p["id"], "kind": "add", "text": tr("{role}：{credit}", role=tr(ROLES[role]), credit=credit_line(a))})
    a = pick("interlude")
    if "interlude" not in have and a is not None:
        cands = break_candidates(m)
        p = _new(a["id"], "interlude", "auto")
        p["at_base"] = m._voice_to_base(cands[0])
        ps.append(p)
        alternatives[p["id"]] = cands[1:]
        why = tr("话题之间的停顿") if chapter_starts(m) else tr("对话里较长的停顿")
        changes.append({"pid": p["id"], "kind": "add", "text": tr("间奏：{p0}，放在{why}处", p0=credit_line(a), why=why),
                        "voice_s": cands[0]})
    for kind in ("bed", "dialogue", "trailer"):
        if any(x.get("kind") == kind for x in assets) and ROLE_FOR_KIND[kind] not in have:
            left.append(tr(KINDS[kind]))
    if not changes:
        msg = tr("按用途能自动放的都已经放好了。") if have else tr("素材库里还没有标成片头、片尾或休息间隙的音乐。")
        if left:
            msg += tr("{p0}要放在哪由你定，可以在下面跟 LACUNA 说。", p0=join_list(left))
        return {"draft": None, "message": msg}
    msg = tr("按素材的用途放好了，先试听，满意再点「采用」。")
    if left:
        msg += tr("{p0}放哪要你定，可以在下面跟 LACUNA 说。", p0=join_list(left))
    m.set_draft(ps, changes, msg, "auto", alternatives)
    return {"draft": m.draft_view(), "message": msg}


# ===================================================================== talking about the music

SYSTEM = """\
You arrange the music of one episode of 《洛城二三事》, a casual two-host Chinese film podcast \
(hosts Leon and Pei). The host tells you, in Chinese, how to change it ("间奏晚两秒", "背景音小一点", \
"片尾换成另一首", "在聊完奥德赛之后加一段间奏"). You cannot hear audio; you get the current music \
placements, the music library (names, the use Leon gave each file, his notes, credits), the \
chapter headings and the transcript near each placement and near pauses. All times are seconds on \
the final mix (what the host hears, m:ss given as well).

Every piece of music plays whole (src_in_s to src_out_s, by default the whole file); under talk it \
keeps playing as background, bg_db lower than full level, at a constant level. Roles: intro (starts \
at 0, full level alone for solo_s, then down to background over ramp_s while the voice starts), \
interlude (at a point between two sentences the talk stops; it rises over ramp_s, plays at full \
level for solo_s, goes back down over ramp_out_s and the talk resumes over it; pre_s = how long it \
already plays under the talk before the point), outro (background under the last words, placed so \
the voice ends at second bye_s of the file, then full level to src_out_s, fading out over \
fade_out_s), bed (background under the talk from a point, optionally to an end), clip (a film line \
or trailer inserted with a little silence).

Answer by calling arrange_music once. Actions:
- add: put library asset `asset_id` in `role`; interlude / bed / clip need at_s (and bed may have until_s).
- move: move placement `placement_id`: either to at_s, or by shift_s (positive = later).
- set: change placement `placement_id`: gain_db (absolute, 0 = default level) or gain_change_db \
(relative, "小一点" ≈ -3, "大一点" ≈ +3), src_in_s / src_out_s (which part of the file plays; \
"裁到 2:30" = src_out_s 150), solo_s, ramp_s, bg_db ("背景再小一点" ≈ +3), pre_s, bye_s, fade_out_s.
- remove: take placement `placement_id` out.
Leave unused fields null. Use an empty list when nothing should change, and when it is unclear \
which music or where, ask one short question in `message` instead of guessing. Positions are \
snapped to the nearest pause automatically. `message` (Simplified Chinese, one or two short \
sentences) says what will change and where (m:ss). The host hears your suggestion before it is \
applied.""" + AI_NAME_RULE  # i18n-ignore

_N = {"type": ["number", "null"]}
SET_FIELDS = ("src_in_s", "src_out_s", "solo_s", "ramp_s", "ramp_out_s", "bg_db", "pre_s", "bye_s", "fade_out_s")
SET_TEXT = {"src_in_s": N_("从文件第 {s} 秒"), "src_out_s": N_("到文件第 {s} 秒"), "solo_s": N_("全音量 {s} 秒"),
            "ramp_s": N_("升降 {s} 秒"), "ramp_out_s": N_("淡出到背景 {s} 秒"), "bg_db": N_("背景压低 {s} dB"), "pre_s": N_("间隙前垫 {s} 秒"),
            "bye_s": N_("拜拜落在歌的第 {s} 秒"), "fade_out_s": N_("淡出 {s} 秒")}
_S = {"type": ["string", "null"]}
TOOL = {
    "name": "arrange_music",
    "description": "Change the episode's music (possibly several actions), or nothing.",
    "strict": True,
    "input_schema": {
        "type": "object", "additionalProperties": False, "required": ["message", "actions"],
        "properties": {
            "message": {"type": "string", "description": "Reply to the host, Simplified Chinese."},
            "actions": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["type", "placement_id", "asset_id", "role", "at_s", "until_s", "shift_s", "gain_db",
                             "gain_change_db", *SET_FIELDS],
                "properties": {
                    "type": {"type": "string", "enum": ["add", "move", "set", "remove"]},
                    "placement_id": _S, "asset_id": _S,
                    "role": {"type": ["string", "null"], "enum": [*ROLES, None]},
                    "at_s": _N, "until_s": _N, "shift_s": _N, "gain_db": _N, "gain_change_db": _N,
                    **{k: _N for k in SET_FIELDS},
                }}},
        },
    },
}


def context(m: EpisodeMusic, instruction: str) -> dict:
    """What Claude gets: text and numbers only."""
    sr = m.ep.sr
    lay = m.layout()
    utts, _ = _utterances(m)
    final = lambda v: round(lay.final(int(round(v * sr))) / sr, 2)   # noqa: E731

    def near(t_final: float) -> list[dict]:
        return [{"speaker": u.speaker, "at": final(u.start), "text": u.text} for u in utts
                if abs(final(u.start) - t_final) <= NEAR_S]

    placements = []
    for p in m.items_json(lay, include_proposed=False):
        if p.get("missing"):
            continue
        at = p.get("at_s") if p.get("at_s") is not None else p["start_s"]
        placements.append({"id": p["id"], "role": p["role"], "role_label": p["role_label"], "asset_id": p["asset_id"],
                           "music": p["credit_line"], "file": p["asset_name"], "position_s": at,
                           "position": _mmss(at), "plays_s": [p["start_s"], p["end_s"]], "gain_db": p["gain_db"],
                           **{k: p.get(k) for k in SET_FIELDS},
                           "file_duration_s": p["asset_duration_s"], "talk_nearby": near(at)})
    library = [{"asset_id": a["id"], "file": a["name"], "use": KINDS.get(a.get("kind"), ""), "note": a.get("note") or "",
                "music": credit_line(a), "duration_s": a["duration_s"]} for a in m.lib.assets()]
    chapters = []
    try:
        from .publish import Publisher
        pack = Publisher(m.ws).view(m.ep).get("pack") or {}
        chapters = [{"at_s": c["t"], "at": c["time"], "heading": c["heading"]} for c in pack.get("chapters", [])]
    except Exception:   # noqa: BLE001
        pass
    breaks = sorted(pauses(m), key=lambda x: -x[1])[:15]
    return {"instruction": instruction, "duration_s": round(lay.length / sr, 2), "duration": _mmss(lay.length / sr),
            "placements": placements, "library": library, "chapters": chapters,
            "longest_pauses": [{"at_s": final(t), "at": _mmss(final(t)), "length_s": round(n, 2),
                                "talk_before": next((u.text[-40:] for u in reversed(utts) if u.end <= t), "")}
                               for t, n in sorted(breaks)]}


def apply_actions(m: EpisodeMusic, actions: list[dict]) -> tuple[list[dict], list[dict]]:
    """The placements after Claude's actions, and a readable change list. Raises ValueError for an
    action that names something that doesn't exist."""
    current = [p for p in m.placements() if p.get("status", APPLIED) == APPLIED]
    ps = copy.deepcopy(current)
    sr = m.ep.sr
    lay = m.layout(placements=current)
    by = {p["id"]: p for p in ps}
    anchors = {it.p["id"]: it.anchor for it in lay.items}
    assets = {a["id"]: a for a in m.lib.assets()}
    changes = []

    def voice_at(final_s: float, exclude: str | None) -> float:
        return snap(m, m.final_to_voice_s(final_s, exclude=exclude, placements=current))

    for a in actions:
        t = a.get("type")
        if t == "add":
            asset = assets.get(a.get("asset_id") or "")
            role = a.get("role")
            if asset is None or role not in ROLES:
                raise ValueError(tr("要放的音乐或用途不对"))
            p = _new(asset["id"], role, "chat")
            if role in ANCHORED:
                if a.get("at_s") is None:
                    raise ValueError(tr("{p0}需要一个位置", p0=tr(ROLES[role])))
                p["at_base"] = m._voice_to_base(voice_at(a["at_s"], None))
                if role == "bed" and a.get("until_s") is not None:
                    p["until_base"] = m._voice_to_base(voice_at(a["until_s"], None))
            if role in ("intro", "outro"):
                ps = [x for x in ps if x["role"] != role]
            for k in ("gain_db", *SET_FIELDS):
                if a.get(k) is not None:
                    p[k] = a[k]
            ps.append(p)
            by[p["id"]] = p
            changes.append({"pid": p["id"], "kind": "add", "text": tr("加{p0}：{p1}", p0=tr(ROLES[role]), p1=credit_line(asset))
                            + (tr("，在 {p0}", p0=_mmss(a['at_s'])) if a.get("at_s") is not None else "")})
            continue
        p = by.get(a.get("placement_id") or "")
        if p is None:
            raise ValueError(tr("没有这段配乐：{p0}", p0=a.get('placement_id')))
        label = tr(ROLES[p["role"]])
        if t == "remove":
            ps = [x for x in ps if x["id"] != p["id"]]
            changes.append({"pid": p["id"], "kind": "remove", "text": tr("去掉{label}", label=label)})
        elif t == "move":
            if p["role"] not in ANCHORED:
                raise ValueError(tr("{label}的位置是固定的（开头 / 结尾），可以改全音量秒数或拜拜的位置", label=label))
            old = (anchors.get(p["id"]) or 0) / sr
            to = a["at_s"] if a.get("at_s") is not None else old + float(a.get("shift_s") or 0.0)
            p["at_base"] = m._voice_to_base(voice_at(max(to, 0.0), p["id"]))
            changes.append({"pid": p["id"], "kind": "move", "text": tr("{label}从 {p1} 挪到约 {p2}", label=label, p1=_mmss(old), p2=_mmss(to))})
        elif t == "set":
            bits = []
            if a.get("gain_db") is not None or a.get("gain_change_db") is not None:
                g = a["gain_db"] if a.get("gain_db") is not None else float(p.get("gain_db") or 0) + a["gain_change_db"]
                p["gain_db"] = round(min(max(g, -30.0), 12.0), 1)
                bits.append(tr("音量 {gain_db} dB", gain_db=f"{p['gain_db']:+.0f}"))
            for k, what in SET_TEXT.items():
                if a.get(k) is not None:
                    p[k] = a[k]
                    bits.append(tr(what, s=f"{a[k]:.1f}"))
            if not bits:
                raise ValueError(tr("没有说要改什么"))
            changes.append({"pid": p["id"], "kind": "set", "text": tr("{label}：{changes}", label=label,
                                                                changes=(", " if lang() == "en" else "，").join(bits))})
        else:
            raise ValueError(tr("不认识的动作 {t}", t=t))
    return ps, changes


class MusicChat:
    model = "claude-opus-5-5"

    def __init__(self, client: Any = None):
        self._client = client

    def available(self) -> bool:
        if self._client is not None:
            return True
        from .editor import find_api_key, sdk_installed
        return bool(find_api_key()[0]) and sdk_installed()

    def client(self):
        if self._client is None:
            from .editor import find_api_key
            import anthropic
            self._client = anthropic.Anthropic(api_key=find_api_key()[0], timeout=120.0, max_retries=1)
        return self._client

    def ask(self, m: EpisodeMusic, instruction: str) -> dict:
        """-> {"message", "draft" (or None), "usage"}. Failures come back as a message."""
        from .editor import ClaudeEditorAdapter, error_message
        if not self.available():
            return {"message": tr("还没接上 AI（没有 AI 密钥），LACUNA 暂时不能改配乐。"),
                    "draft": None, "usage": None}
        req = dict(model=self.model, max_tokens=4000, system=in_reply_language(SYSTEM), output_config={"effort": "low"},
                   tools=[in_reply_language(TOOL)], tool_choice={"type": "tool", "name": "arrange_music"},
                   messages=[{"role": "user", "content": json.dumps(context(m, instruction), ensure_ascii=False)}])
        t0 = time.monotonic()
        try:
            resp = self.client().beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                                      fallbacks="default", **req)
        except Exception as e:      # noqa: BLE001
            return {"message": error_message(e), "draft": None, "usage": None}
        usage = ClaudeEditorAdapter._usage(resp, time.monotonic() - t0)
        out = next((dict(b.input) for b in resp.content if b.type == "tool_use" and b.name == "arrange_music"), None)
        if out is None:
            text = "".join(getattr(b, "text", "") for b in resp.content if b.type == "text").strip()
            return {"message": text or tr("LACUNA 没有给出修改。"), "draft": None, "usage": usage}
        msg = out.get("message") or ""
        if not out.get("actions"):
            return {"message": msg or tr("没有要改的。"), "draft": None, "usage": usage}
        try:
            ps, changes = apply_actions(m, out["actions"])
            m.set_draft(ps, changes, msg, "chat")
        except (ValueError, ConflictError, KeyError) as e:
            return {"message": tr("{msg}（没法照做：{e}）", msg=msg, e=e) if msg else tr("没法照做：{e}", e=e), "draft": None, "usage": usage}
        return {"message": msg, "draft": m.draft_view(), "usage": usage}
