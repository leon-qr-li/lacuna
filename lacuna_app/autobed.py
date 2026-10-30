"""自动铺底 (docs/decisions/2026-10-30-auto-bed.md): Leon ticks some songs and clicks once; each ticked song is put
in once, as a bed, at a random place in the talk no other music covers (片头 / 片尾 / 间隙 / 间奏 and its
background), straight onto the episode (no suggestion step). Free stretches shorter than 20 s get nothing.
When the songs are longer than the free talk together, they follow each other with a 2 s crossfade and the ones
that don't fit stay out; a song cut at a stretch's end fades out over 3 s. Clicking again replaces the earlier
自动铺底 beds with a new random spread; 「取消所有铺底」 removes every bed. The beds sit at the bed default
(music.BED_BG_DB) and are evened out like any bed; each can be changed or removed like any other.
"""
from __future__ import annotations

import random
import uuid

from .i18n import join_list, tr
from .library import credit_line
from .music import APPLIED, ROLES, TUNING, EpisodeMusic, _free
from .music_assist import snap

SOURCE = "autobed"
XFADE_S = 2.0
MIN_S = 20.0             # Leon 2026-10-30: a free stretch shorter than this stays without a bed
END_FADE_S = 3.0
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
    return {"songs": songs, "free_s": round(sum(b - a for a, b in st) / sr, 1), "stretches": len(st),
            "beds": sum(p["role"] == "bed" for p in ps)}


def _spread(songs: list[tuple[dict, int]], st: list[tuple[int, int]], xf: int, rnd: random.Random, min_n: int) -> list[tuple[dict, int, int, int]]:
    """(song, start, length) for each song that fits: songs in the given (random) order, each in the stretch with
    the most room left (cut to it when none holds it whole), then spread out inside its stretch with random room
    between them; with no room to spare, back to back with a crossfade."""
    room = [b - a for a, b in st]
    per: list[list[tuple[dict, int]]] = [[] for _ in st]
    for song, n in songs:
        k = max(range(len(st)), key=lambda i: (room[i] >= n, room[i]))
        full, n = n, min(n, room[k] + (xf if per[k] else 0))
        if n < min(full, min_n):                              # only a scrap of this song would fit
            continue
        per[k].append((song, n))
        room[k] -= n - (xf if len(per[k]) > 1 else 0)
    out = []
    for (a, b), items in zip(st, per):
        if not items:
            continue
        need = sum(n for _, n in items) - xf * (len(items) - 1)
        slack = max(b - a - need, 0)
        cuts = sorted(rnd.random() for _ in range(len(items) + 1))
        w = [cuts[0]] + [cuts[i] - cuts[i - 1] for i in range(1, len(cuts))]
        scale = slack / max(sum(w), 1e-9)
        t = a
        for i, (song, n) in enumerate(items):
            t += int(w[i] * scale)
            out.append((song, t, min(n, b - t), b))
            t += n - xf
    return out


def fill(m: EpisodeMusic, asset_ids: list[str], seed: int | None = None) -> dict:
    """Put each ticked song in once, at random, replacing earlier 自动铺底 beds. Returns {"placed", "message"}."""
    assets = {a["id"]: a for a in m.lib.for_episode(m.ep.id)}
    songs = [assets[i] for i in dict.fromkeys(asset_ids) if i in assets and assets[i]["duration_s"] >= 1.0]
    if not songs:
        return {"placed": 0, "message": tr("先勾几首要铺的歌。")}
    with m.lock:
        doc = m.load()
        keep = [p for p in doc["placements"] if p.get("source") != SOURCE]
        lay = m.layout(placements=[p for p in keep if p.get("status", APPLIED) == APPLIED])
        sr = m.ep.sr
        st = stretches(m, lay)
        if not st:
            return {"placed": 0, "message": tr("没有空档可铺：说话的地方都已经有配乐了。")}
        rnd = random.Random(seed)
        order = songs[:]
        rnd.shuffle(order)
        xf = int(XFADE_S * sr)
        spread = sorted(_spread([(s, int(s["duration_s"] * sr)) for s in order], st, xf, rnd, int(MIN_S * sr)), key=lambda x: x[1])
        placed, prev_end = [], 0
        for s, t, n, b in spread:          # a song with room around it starts at the nearest pause between sentences
            if t >= prev_end:
                t2 = lay.final(int(round(snap(m, lay.voice(t) / sr) * sr)))
                if prev_end <= t2 and t2 + n <= b and _stretch_of(st, t2) == _stretch_of(st, t):
                    t = t2
            placed.append((s, t, n))
            prev_end = t + n
        new = []
        for i, (s, t, n) in enumerate(placed):
            p = {"id": "mu_" + uuid.uuid4().hex[:8], "asset_id": s["id"], "role": "bed",
                 "at_base": _base(m, lay, t), "until_base": _base(m, lay, t + n - 1) + 1,   # the last sample: not past a gap there
                 **{k: None for k in TUNING}, "gain_db": 0.0, "auto": False, "loop": False, "status": APPLIED,
                 "source": SOURCE}
            nxt = placed[i + 1][1] if i + 1 < len(placed) else None
            if nxt is not None and nxt < t + n:
                p["fade_out_s"] = XFADE_S                       # crossfades into the next song
            elif n < int(s["duration_s"] * sr) - 1:
                p["fade_out_s"] = END_FADE_S                    # cut at a stretch's end
            m._clean(p, s)
            new.append(p)
        doc["placements"] = keep + new
        m.save(doc)
    left = len(songs) - len(new)
    msg = tr("铺好了 {n} 首，随机放在 {k} 段空着的说话里。", n=len(new), k=len({_stretch_of(st, t) for _, t, _ in placed}))
    if left:
        msg += tr("还有 {n} 首放不下：空档不够长。", n=left)
    return {"placed": len(new), "message": msg}


def _stretch_of(st: list[tuple[int, int]], t: int) -> int:
    return next((i for i, (a, b) in enumerate(st) if a <= t < b), -1)


def clear(m: EpisodeMusic) -> int:
    """「取消所有铺底」: remove every bed of the episode (自动铺底 or placed by hand). Returns how many."""
    with m.lock:
        doc = m.load()
        n = sum(p["role"] == "bed" for p in doc["placements"])
        doc["placements"] = [p for p in doc["placements"] if p["role"] != "bed"]
        d = doc.get("draft")
        if d and any(p["role"] == "bed" for p in d.get("placements", [])):
            doc["draft"] = None             # a suggestion with beds would bring them back
        m.save(doc)
    return n
