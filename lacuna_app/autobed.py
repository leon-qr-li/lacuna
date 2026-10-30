"""自动铺底 (docs/decisions/2026-10-30-auto-bed.md): Leon ticks some songs, the App puts them, in a random order, as
beds into every stretch of talk no other music covers (片头 / 片尾 / 间隙 / 间奏 and its background). Songs follow
each other with a 2 s crossfade; a stretch's last song fades out over 3 s at its end; when the ticked songs run
out they go round again in a new order. A suggestion like 「按用途自动放好」: heard first, applied when accepted;
asking again gives a new order. The beds sit at the bed default (music.BED_BG_DB) and are evened out like any bed.
"""
from __future__ import annotations

import copy
import random
import uuid

from .i18n import join_list, tr
from .library import credit_line
from .music import APPLIED, ROLES, TUNING, EpisodeMusic, _free

SOURCE = "autobed"
XFADE_S = 2.0
MIN_S = 20.0             # Leon 2026-10-30: a free stretch shorter than this stays without a bed
END_FADE_S = 3.0
TAIL_S = 6.0            # after a song, less talk than this left in the stretch: no further song
_mmss = lambda s: f"{int(s) // 60}:{int(s) % 60:02d}"   # noqa: E731


def _base(m: EpisodeMusic, lay, f: int) -> int:
    return m._voice_to_base(lay.voice(f) / m.ep.sr)


def stretches(m: EpisodeMusic, lay) -> list[tuple[int, int]]:
    """Final-mix stretches with talk and no other music (nor an empty gap), at least MIN_S long."""
    sr = m.ep.sr
    taken = sorted([(it.start, it.end) for it in lay.items if it.p.get("source") != SOURCE]
                   + [(x["start"], x["start"] + x["length"]) for x in lay.gaps if not x["filled_by"]])
    merged: list[list[int]] = []
    for a, b in taken:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in _free([(a, b) for a, b in merged], lay.final(lay.voice_len)) if b - a >= int(MIN_S * sr)]


def view(m: EpisodeMusic) -> dict:
    """What the 自动铺底 card shows: the songs this episode can use (and what each is already used as), the free
    stretches and how long they are together."""
    ps = [p for p in m.placements() if p.get("status", APPLIED) == APPLIED]
    used = {}
    for p in ps:
        if p.get("source") != SOURCE:
            used.setdefault(p["asset_id"], tr(ROLES[p["role"]]))
    lay = m.layout(placements=[p for p in ps if p.get("source") != SOURCE])
    sr = m.ep.sr
    st = stretches(m, lay)
    mine = {p["asset_id"] for p in ps if p.get("source") == SOURCE}
    songs = [{"id": a["id"], "name": a["name"], "kind": a["kind"], "kind_label": m.lib.asset_view(a)["kind_label"],
              "duration_s": a["duration_s"], "used_as": used.get(a["id"]), "in_bed": a["id"] in mine}
             for a in m.lib.for_episode(m.ep.id) if a.get("kind") not in ("dialogue", "trailer")]
    return {"songs": songs, "free_s": round(sum(b - a for a, b in st) / sr, 1), "stretches": len(st)}


def suggest(m: EpisodeMusic, asset_ids: list[str], seed: int | None = None) -> dict:
    """The suggestion: earlier 自动铺底 beds replaced by a new random fill. Returns {"draft", "message"}."""
    current = [p for p in m.placements() if p.get("status", APPLIED) == APPLIED]
    keep = [p for p in current if p.get("source") != SOURCE]
    assets = {a["id"]: a for a in m.lib.for_episode(m.ep.id)}
    songs = [assets[i] for i in dict.fromkeys(asset_ids) if i in assets and assets[i]["duration_s"] >= 1.0]
    if not songs:
        return {"draft": None, "message": tr("先勾几首要铺的歌。")}
    lay = m.layout(placements=keep)
    sr = m.ep.sr
    st = stretches(m, lay)
    if not st:
        return {"draft": None, "message": tr("没有空档可铺：说话的地方都已经有配乐了。")}
    rnd = random.Random(seed)
    queue: list[dict] = []

    def next_song() -> dict:
        if not queue:
            order = songs[:]
            rnd.shuffle(order)
            queue.extend(order)
        return queue.pop(0)

    xf = int(XFADE_S * sr)
    ps = copy.deepcopy(keep)
    changes = []
    for a, b in st:
        t, mine = a, []
        while True:
            s = next_song()
            n = min(int(s["duration_s"] * sr), b - t)
            p = {"id": "mu_" + uuid.uuid4().hex[:8], "asset_id": s["id"], "role": "bed",
                 "at_base": _base(m, lay, t), "until_base": _base(m, lay, t + n - 1) + 1,   # the last sample: not past a gap there
                 **{k: None for k in TUNING}, "gain_db": 0.0, "auto": False, "loop": False, "status": APPLIED,
                 "source": SOURCE}
            mine.append((p, s))
            if t + n >= b or b - (t + n - xf) < int(TAIL_S * sr):  # the stretch is full (a last few seconds stay quiet)
                if n < int(s["duration_s"] * sr):
                    p["fade_out_s"] = END_FADE_S                        # cut at the stretch's end: fades out over 3 s
                break
            p["fade_out_s"] = XFADE_S                                   # crossfades into the next song
            t = t + n - xf
        ps.extend(p for p, _ in mine)
        changes.append({"pid": mine[0][0]["id"], "kind": "add", "voice_s": round(lay.voice(a) / sr, 3),
                        "text": tr("{a}–{b} 铺底：{songs}", a=_mmss(a / sr), b=_mmss(b / sr),
                                   songs=join_list([credit_line(s) for _, s in mine]))})
    msg = tr("用 {n} 首歌随机铺满了 {k} 个空档，先试听，满意再点「采用」；不满意可以再随机一次。", n=len(songs), k=len(st))
    m.set_draft(ps, changes, msg, "auto")
    return {"draft": m.draft_view(), "message": msg}
