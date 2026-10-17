"""S5 scorer — compare an AI first cut (edit ops JSON) with Leon's real edit of EP001.

Everything is scored PER TRACK IN RAW TIME on a 10 ms grid.

Ground truth (from spikes/s4_alignment/out/ep001_alignment.json):
  removed[X]   = removed_raw[X]  ∪  verified muted spans of X (raw speech Leon silenced in place)
  ambiguous[X] = unverified muted spans of X (alignment cannot tell) -> never counted against the AI
  GT interjection moves are derived from the per-track offsets (see interjections()).

AI ops are resolved to per-track removed masks:
  cut -> [from, to]; tighten_pause -> middle (len - target) of the pause; slip -> no removal
  (scored only in the interjection section); keep_flag -> no removal (counted).

Leniency (S4 REPORT "Implications" 1):
  * speech frames (inside a token span of that track): a removed frame counts as matching if the
    other side removed something within ±tol (default 0.10 s).
  * non-speech frames (a pause on that track, incl. long stretches where the track is silent while
    the other host talks): position inside the pause is ignored; per pause the matched amount is
    min(AI removed, GT removed).

Metrics: seconds-weighted precision/recall (overall, speech-only, pause-only), event-level P/R with
tolerance windows, FALSE DELETIONS (AI removed speech Leon kept; high-severity), missed removals,
final duration, pause-length distribution (paired per floor gap), per-category breakdown,
interjection handling agreement (deleted / moved / kept).

Usage:
  python score.py --ops ops.json [--gt ../s4_alignment/out/ep001_alignment.json]
                  [--tokens out/ep001_tokens.json] [--json report.json] [--top 15]
                  [--min-raw 2200] [--max-raw 4412]

Time window (--min-raw / --max-raw, raw seconds, both optional): AI removals, GT removals and GT
ambiguous spans are all clipped to [min_raw, max_raw); floor pauses and interjection candidates are
restricted to ones lying inside the window; duration is reported for the window only (raw = window
length, Leon/AI estimates by the same formula). Without these flags the scorer is unchanged.
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import sys

import numpy as np

HOP = 0.01
HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = {"L": "Leon", "P": "Pei"}
CATS = ["pause", "disfluency", "repetition", "crosstalk", "content", "interjection_move", "single_track_noise"]


# --------------------------------------------------------------------------- helpers

def fr(t):
    return int(round(t / HOP))


def runs(mask):
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def dilate(mask, k):
    if k <= 0:
        return mask.copy()
    c = np.convolve(mask.astype(np.int32), np.ones(2 * k + 1, np.int32), mode="same")
    return c > 0


def merge_runs(rs, gap):
    out = []
    for a, b in rs:
        if out and a - out[-1][1] <= gap:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


class Track:
    def __init__(self, tag, toks, n):
        self.tag = tag
        self.toks = toks
        self.ids = {t["id"]: i for i, t in enumerate(toks)}
        self.starts = [t["start"] for t in toks]
        self.speech = np.zeros(n, bool)
        for t in toks:
            self.speech[fr(t["start"]):fr(t["end"])] = True

    def text(self, a, b):
        """tokens overlapping frames [a, b)"""
        i0 = max(0, bisect.bisect_right(self.starts, a * HOP) - 1)
        out, first = [], None
        for t in self.toks[i0:]:
            if t["start"] >= b * HOP:
                break
            if t["end"] > a * HOP:
                first = first or t["id"]
                out.append(t["t"])
        return first, "".join(out)

    def gap_at(self, t):
        """(gap_start, gap_end) of the pause on this track containing raw time t, or None if t is in a token."""
        i = bisect.bisect_right(self.starts, t) - 1
        if i >= 0 and self.toks[i]["end"] > t:
            return None
        a = self.toks[i]["end"] if i >= 0 else 0.0
        b = self.toks[i + 1]["start"] if i + 1 < len(self.toks) else float("inf")
        return (a, b)


# --------------------------------------------------------------------------- ground truth

def load_gt(path, n):
    d = json.load(open(path, encoding="utf-8"))
    rem = {k: np.zeros(n, bool) for k in NAMES}
    amb = {k: np.zeros(n, bool) for k in NAMES}
    for tag, nm in NAMES.items():
        for a, b in d["removed_raw"][nm]:
            rem[tag][fr(a):fr(b)] = True
    for m in d["muted_track_spans"]:
        tag = "L" if m["track"] == "Leon" else "P"
        a, b = m["raw"]
        (rem if m["same_offset_heard_both_sides"] else amb)[tag][fr(a):fr(b)] = True
    segs = [s for s in d["segments"] if s["type"] == "raw"]
    return d, rem, amb, segs


def raw_to_final(segs, tag, r):
    k = "leon_src" if tag == "L" else "pei_src"
    for s in segs:
        a, b = s[k]
        if a <= r < b:
            return s["final_start"] + (r - a)
    return None


def final_to_raw(segs, tag, f):
    k = "leon_src" if tag == "L" else "pei_src"
    for s in segs:
        if s["final_start"] <= f < s["final_end"]:
            return s[k][0] + (f - s["final_start"])
    return None


# --------------------------------------------------------------------------- AI ops

def resolve_ops(ops, tracks, n):
    rem = {k: np.zeros(n, bool) for k in NAMES}
    cat = {k: np.full(n, -1, np.int8) for k in NAMES}
    opi = {k: np.full(n, -1, np.int32) for k in NAMES}
    slips, flags, warnings = [], [], []

    def point(p, end, tag):
        if isinstance(p, str):
            tr = tracks[p[0]]
            if p not in tr.ids:
                raise KeyError(p)
            t = tr.toks[tr.ids[p]]
            return t["end"] if end else t["start"]
        return float(p)

    def apply(tags, a, b, k, c):
        if b <= a:
            return
        for tg in tags:
            rem[tg][fr(a):fr(b)] = True
            cat[tg][fr(a):fr(b)] = c
            opi[tg][fr(a):fr(b)] = k

    for k, o in enumerate(ops):
        tags = ["L", "P"] if o.get("track") == "both" else [o.get("track")]
        c = CATS.index(o["category"]) if o.get("category") in CATS else -1
        try:
            if o["op"] == "cut":
                a, b = point(o["from"], False, tags[0]), point(o["to"], True, tags[0])
                if b <= a:
                    warnings.append(f"{o['id']}: empty/reversed range {a:.2f}-{b:.2f} — skipped")
                apply(tags, a, b, k, c)
            elif o["op"] == "tighten_pause":
                at = o["at"]
                if isinstance(at, str):
                    t = point(at, True, at[0]) + 0.005

                else:
                    t = float(at)
                gaps = []
                for tg in (tags if o["track"] != "both" else ["L", "P"]):
                    gaps.append(tracks[tg].gap_at(t))
                if any(g is None for g in gaps):
                    warnings.append(f"{o['id']}: 'at' not inside a pause on {o['track']} — skipped")
                    continue
                a = max(g[0] for g in gaps)
                b = min(g[1] for g in gaps)
                if not np.isfinite(b):
                    b = a + 0.0
                excess = (b - a) - float(o["target_s"])
                if excess > 0:
                    mid = (a + b) / 2
                    apply(tags, mid - excess / 2, mid + excess / 2, k, c)
            elif o["op"] == "slip":
                a, b = point(o["from"], False, tags[0]), point(o["to"], True, tags[0])
                slips.append({"track": tags[0], "start": a, "end": b, "delta_s": float(o["delta_s"]), "id": o["id"]})
            elif o["op"] == "keep_flag":
                flags.append(o)
            else:
                warnings.append(f"{o.get('id')}: unknown op {o.get('op')}")
        except (KeyError, ValueError, TypeError) as e:
            warnings.append(f"{o.get('id')}: cannot resolve ({e!r}) — skipped")
    return rem, cat, opi, slips, flags, warnings


# --------------------------------------------------------------------------- interjections

def interjections(tracks, n, max_tokens=6, max_dur=2.5, join_pause=0.5):
    """Short phrases on one track while the other host is talking around them."""
    out = []
    for tag, tr in tracks.items():
        other = tracks["P" if tag == "L" else "L"]
        T = tr.toks
        i = 0
        while i < len(T):
            j = i
            while j + 1 < len(T) and T[j]["pause_after"] is not None and T[j]["pause_after"] < join_pause:
                j += 1
            a, b = T[i]["start"], T[j]["end"]
            prev_gap = (a - T[i - 1]["end"]) if i > 0 else 99
            if j - i + 1 <= max_tokens and b - a <= max_dur and prev_gap >= join_pause:
                ctx = other.speech[max(0, fr(a - 1.0)):fr(b + 1.0)].sum() * HOP
                if ctx >= 1.0:
                    out.append({"track": tag, "start": a, "end": b, "first": T[i]["id"], "last": T[j]["id"],
                                "text": "".join(t["t"] for t in T[i:j + 1])})
            i = j + 1
    return out


def gt_interjection_state(u, rem, segs, tracks):
    tag = u["track"]
    sp = tracks[tag].speech[fr(u["start"]):fr(u["end"])]
    rm = rem[tag][fr(u["start"]):fr(u["end"])]
    if sp.sum() == 0:
        return "kept", 0.0
    if (sp & rm).sum() / sp.sum() >= 0.5:
        return "deleted", 0.0
    # mid of kept speech frames
    kept = np.where(sp & ~rm)[0]
    r = (fr(u["start"]) + kept[len(kept) // 2]) * HOP
    f = raw_to_final(segs, tag, r)
    if f is None:
        return "unclear", 0.0
    ro = final_to_raw(segs, "P" if tag == "L" else "L", f)
    if ro is None:
        return "unclear", 0.0
    delta = ro - r            # >0: the interjection plays later relative to the other host than in raw
    if abs(delta) > 3.0:
        return "unclear", delta
    return ("moved" if abs(delta) >= 0.3 else "kept"), delta


# --------------------------------------------------------------------------- scoring

def score(ops_doc, gt_path, tok_path, tol_s=0.10, ev_tol_s=0.30, top=15, min_raw=None, max_raw=None):
    tok = json.load(open(tok_path, encoding="utf-8"))
    n = fr(max(t["end"] for tr in tok["tracks"].values() for t in tr) + 5)
    gtd, gt_rem, gt_amb, segs = load_gt(gt_path, n)
    n = max(n, fr(gtd["stats"]["raw_duration_s"]) + 10)
    tracks = {k: Track(k, tok["tracks"][k], n) for k in NAMES}
    ai_rem, ai_cat, ai_op, slips, flags, warns = resolve_ops(ops_doc["ops"], tracks, n)
    windowed = min_raw is not None or max_raw is not None
    w0 = fr(min_raw) if min_raw is not None else 0
    w1 = min(n, fr(max_raw)) if max_raw is not None else n
    if windowed:
        W = np.zeros(n, bool)
        W[w0:w1] = True
        for tag in NAMES:
            ai_rem[tag] &= W
            gt_rem[tag] &= W
            gt_amb[tag] &= W
        slips = [s for s in slips if s["start"] >= w0 * HOP and s["end"] <= w1 * HOP]
    ops = ops_doc["ops"]
    k_tol, k_ev = fr(tol_s), fr(ev_tol_s)
    R = {"n_ops": len(ops), "ops_by_type": {}, "warnings": warns[:50], "n_warnings": len(warns),
         "keep_flags": len(flags), "tracks": {}}
    if windowed:
        R["window_raw_s"] = [round(w0 * HOP, 2), round(w1 * HOP, 2)]
    for o in ops:
        R["ops_by_type"][o["op"]] = R["ops_by_type"].get(o["op"], 0) + 1

    cat_credit = {c: [0.0, 0, 0.0, 0.0] for c in CATS + ["?"]}   # credit, frames, speech_s, false_del_s
    all_fd, all_miss = [], []
    for tag in NAMES:
        tr = tracks[tag]
        A, G, M, S = ai_rem[tag], gt_rem[tag], gt_amb[tag], tr.speech
        GM = G | M
        dGM, dA = dilate(GM, k_tol), dilate(A, k_tol)
        # per-pause leniency
        sil = ~S
        gid = np.cumsum(np.diff(np.concatenate([[0], sil.astype(np.int8)])) == 1) * sil   # gap index, 0 = speech
        ng = gid.max() + 1
        a_g = np.bincount(gid[A & sil], minlength=ng)
        g_g = np.bincount(gid[G & sil], minlength=ng)
        m_g = np.bincount(gid[GM & sil], minlength=ng)
        tp_g = np.minimum(a_g, m_g)          # ambiguous muted spans count as acceptable for the AI
        tpr_g = np.minimum(a_g, g_g)
        tp_g[0] = tpr_g[0] = 0
        # precision credit per AI frame
        credit = np.zeros(n, np.float32)
        sp_hit = A & S & dGM
        credit[sp_hit] = 1.0
        ratio = np.where(a_g > 0, tp_g / np.maximum(a_g, 1), 0.0)
        silA = A & sil
        credit[silA] = ratio[gid[silA]]
        # recall credit per GT frame
        rc = np.zeros(n, np.float32)
        rc[G & S & dA] = 1.0
        rratio = np.where(g_g > 0, tpr_g / np.maximum(g_g, 1), 0.0)
        silG = G & sil
        rc[silG] = rratio[gid[silG]]

        ai_s, gt_s = A.sum() * HOP, G.sum() * HOP
        prec = credit[A].sum() / max(A.sum(), 1)
        rec = rc[G].sum() / max(G.sum(), 1)
        sp_prec = sp_hit.sum() / max((A & S).sum(), 1)
        sp_rec = (G & S & dA).sum() / max((G & S).sum(), 1)
        pa_prec = credit[silA].sum() / max(silA.sum(), 1)
        pa_rec = rc[silG].sum() / max(silG.sum(), 1)

        # event level
        gev = [(a, b) for a, b in merge_runs(runs(G), fr(0.1)) if b - a >= 5]
        aev = [(a, b) for a, b in merge_runs(runs(A), fr(0.1)) if b - a >= 5]
        dAe, dGe = dilate(A, k_ev), dilate(GM, k_ev)

        def ev_hit(ev, dil, other_gap_counts):
            hit = 0
            for a, b in ev:
                spf = S[a:b].mean()
                if dil[a:b].any():
                    hit += 1
                elif spf < 0.1:      # pause-only event: any removal by the other side in the same pause
                    gs = set(np.unique(gid[a:b]).tolist()) - {0}
                    if any(other_gap_counts[g] > 0 for g in gs):
                        hit += 1
            return hit
        g_hit = ev_hit(gev, dAe, a_g)
        a_hit = ev_hit(aev, dGe, m_g)

        # false deletions / misses
        fd = A & S & ~dGM
        miss = G & S & ~dA
        def listing(mask, kind):
            items = []
            for a, b in merge_runs(runs(mask), fr(0.15)):
                first, txt = tr.text(a, b)
                k = ai_op[tag][a:b]
                k = k[k >= 0]
                op = ops[int(np.bincount(k).argmax())] if len(k) else None
                items.append({"track": tag, "kind": kind, "raw": [round(a * HOP, 2), round(b * HOP, 2)],
                              "dur": round((b - a) * HOP, 2), "first_token": first, "text": txt,
                              "op": op["id"] if op else None, "category": op.get("category") if op else None,
                              "reason": op.get("reason") if op else None})
            return items
        fdl, msl = listing(fd, "false_deletion"), listing(miss, "missed_removal")
        all_fd += fdl
        all_miss += msl

        for ci in range(-1, len(CATS)):
            m = A & (ai_cat[tag] == ci)
            c = CATS[ci] if ci >= 0 else "?"
            cat_credit[c][0] += float(credit[m].sum())
            cat_credit[c][1] += int(m.sum())
            cat_credit[c][2] += float((m & S).sum() * HOP)
            cat_credit[c][3] += float((m & fd).sum() * HOP)

        R["tracks"][tag] = {
            "ai_removed_s": round(ai_s, 1), "gt_removed_s": round(gt_s, 1),
            "gt_ambiguous_s": round(M.sum() * HOP, 1),
            "precision_s": round(float(prec), 3), "recall_s": round(float(rec), 3),
            "speech": {"ai_removed_s": round((A & S).sum() * HOP, 1), "gt_removed_s": round((G & S).sum() * HOP, 1),
                       "precision": round(float(sp_prec), 3), "recall": round(float(sp_rec), 3)},
            "pause": {"ai_removed_s": round(silA.sum() * HOP, 1), "gt_removed_s": round(silG.sum() * HOP, 1),
                      "precision": round(float(pa_prec), 3), "recall": round(float(pa_rec), 3)},
            "events": {"ai": len(aev), "gt": len(gev), "precision": round(a_hit / max(len(aev), 1), 3),
                       "recall": round(g_hit / max(len(gev), 1), 3), "tolerance_s": ev_tol_s},
            "false_deletion_s": round(fd.sum() * HOP, 2), "false_deletion_items": len(fdl),
            "missed_speech_removal_s": round(miss.sum() * HOP, 2), "missed_items": len(msl),
        }

    R["false_deletions_top"] = sorted(all_fd, key=lambda x: -x["dur"])[:top]
    R["missed_removals_top"] = sorted(all_miss, key=lambda x: -x["dur"])[:top]
    R["false_deletion_total_s"] = round(sum(x["dur"] for x in all_fd), 2)
    R["by_category"] = {c: {"removed_s": round(v[1] * HOP, 1), "precision": round(v[0] / v[1], 3) if v[1] else None,
                            "speech_removed_s": round(v[2], 1), "false_deletion_s": round(v[3], 1)}
                        for c, v in cat_credit.items() if v[1]}

    # duration
    raw = gtd["stats"]["raw_duration_s"]
    aiL, aiP = R["tracks"]["L"]["ai_removed_s"], R["tracks"]["P"]["ai_removed_s"]
    gL, gP = gtd["stats"]["raw_removed_s"]["Leon"], gtd["stats"]["raw_removed_s"]["Pei"]
    R["duration"] = {"raw_s": raw,
                     "leon_final_from_raw_s": gtd["stats"]["final_from_raw_s"],
                     "leon_final_incl_music_s": gtd["stats"]["final_duration_s"],
                     "leon_est_by_formula_s": round(raw - (gL + gP) / 2, 1),
                     "ai_est_s": round(raw - (aiL + aiP) / 2, 1),
                     "formula": "raw - mean(per-track removed); compare ai_est_s with leon_est_by_formula_s"}
    if windowed:
        # same formula, restricted to the window (GT = removed_raw clipped to the window)
        def clip_sum(spans):
            return sum(max(0.0, min(b, w1 * HOP) - max(a, w0 * HOP)) for a, b in spans)
        raw_w = min(raw, w1 * HOP) - w0 * HOP
        gLw, gPw = clip_sum(gtd["removed_raw"]["Leon"]), clip_sum(gtd["removed_raw"]["Pei"])
        fin_w = clip_sum([s["leon_src"] for s in segs])
        R["duration"] = {"raw_s": round(raw_w, 1),
                         "leon_final_from_raw_s": round(fin_w, 1),
                         "leon_final_incl_music_s": None,
                         "leon_est_by_formula_s": round(raw_w - (gLw + gPw) / 2, 1),
                         "ai_est_s": round(raw_w - (aiL + aiP) / 2, 1),
                         "formula": "window only: raw = window length; final_from_raw = kept Leon-track source "
                                    "inside the window; estimates = raw - mean(per-track removed in window)"}

    # pause distribution, paired per floor gap (neither host speaking, >= 0.3 s)
    both_sil = ~(tracks["L"].speech | tracks["P"].speech)
    rows = []
    for a, b in runs(both_sil):
        if b - a < 30 or a == 0 or b >= n - 10:
            continue
        if windowed and (a < w0 or b > w1):
            continue
        L0 = (b - a) * HOP
        g_after = L0 - (gt_rem["L"][a:b].sum() + gt_rem["P"][a:b].sum()) * HOP / 2
        a_after = L0 - (ai_rem["L"][a:b].sum() + ai_rem["P"][a:b].sum()) * HOP / 2
        rows.append((L0, g_after, a_after))
    rows = np.array(rows)
    def dist(x):
        return {"p10": round(float(np.percentile(x, 10)), 2), "p25": round(float(np.percentile(x, 25)), 2),
                "median": round(float(np.median(x)), 2), "p75": round(float(np.percentile(x, 75)), 2),
                "p90": round(float(np.percentile(x, 90)), 2), "n_gt_1s": int((x > 1.0).sum()),
                "n_gt_2s": int((x > 2.0).sum()), "total_s": round(float(x.sum()), 1)}
    R["floor_pauses"] = {"n": len(rows), "raw": dist(rows[:, 0]), "leon": dist(rows[:, 1]), "ai": dist(rows[:, 2]),
                         "paired_mae_s": round(float(np.mean(np.abs(rows[:, 1] - rows[:, 2]))), 3),
                         "paired_median_signed_s(ai-leon)": round(float(np.median(rows[:, 2] - rows[:, 1])), 3)}

    # interjections
    ij = interjections(tracks, n)
    if windowed:
        ij = [u for u in ij if u["start"] >= w0 * HOP and u["end"] <= w1 * HOP]
    conf = {}
    deltas = []
    for u in ij:
        g, dg = gt_interjection_state(u, gt_rem, segs, tracks)
        sp = tracks[u["track"]].speech[fr(u["start"]):fr(u["end"])]
        rm = ai_rem[u["track"]][fr(u["start"]):fr(u["end"])]
        sl = [s for s in slips if s["track"] == u["track"] and s["start"] < u["end"] and s["end"] > u["start"]]
        if sp.sum() and (sp & rm).sum() / sp.sum() >= 0.5:
            a = "deleted"
        elif sl:
            a = "moved"
        else:
            a = "kept"
        conf.setdefault(g, {}).setdefault(a, 0)
        conf[g][a] += 1
        if g == "moved" and a == "moved":
            deltas.append((dg, sl[0]["delta_s"]))
    dm = np.array(deltas) if deltas else np.zeros((0, 2))
    R["interjections"] = {
        "n_candidates": len(ij), "confusion_gt_rows_ai_cols": conf,
        "gt_moved": sum(conf.get("moved", {}).values()), "ai_moved": sum(v.get("moved", 0) for v in conf.values()),
        "both_moved": len(deltas),
        "sign_agreement": round(float(np.mean(np.sign(dm[:, 0]) == np.sign(dm[:, 1]))), 3) if len(dm) else None,
        "median_abs_delta_error_s": round(float(np.median(np.abs(dm[:, 0] - dm[:, 1]))), 3) if len(dm) else None,
        "definition": "candidate = phrase <=6 tokens, <=2.5 s, preceded by >=0.5 s own pause, with >=1 s of the other "
                      "host's speech within ±1 s. GT moved = kept and relative placement vs the other track changed "
                      "by 0.3-3 s (from S4 per-track offsets); deleted = >=50% of its speech removed.",
    }
    return R


def print_report(R, name):
    p = print
    p(f"=== {name} ===  ops={R['n_ops']} {R['ops_by_type']}  keep_flags={R['keep_flags']}  warnings={R['n_warnings']}"
      + (f"  window={R['window_raw_s']}" if "window_raw_s" in R else ""))
    for tag, t in R["tracks"].items():
        p(f"[{tag}] removed AI {t['ai_removed_s']}s vs Leon {t['gt_removed_s']}s (ambiguous {t['gt_ambiguous_s']}s) | "
          f"P {t['precision_s']:.3f} R {t['recall_s']:.3f} | speech P {t['speech']['precision']:.3f} R {t['speech']['recall']:.3f} "
          f"(AI {t['speech']['ai_removed_s']}s / Leon {t['speech']['gt_removed_s']}s) | pause P {t['pause']['precision']:.3f} "
          f"R {t['pause']['recall']:.3f} | events P {t['events']['precision']:.3f} R {t['events']['recall']:.3f} "
          f"(AI {t['events']['ai']} / Leon {t['events']['gt']}) | FALSE DEL {t['false_deletion_s']}s ({t['false_deletion_items']}) | "
          f"missed speech {t['missed_speech_removal_s']}s")
    d = R["duration"]
    p(f"duration: AI est {d['ai_est_s']}s vs Leon est {d['leon_est_by_formula_s']}s (Leon actual from raw {d['leon_final_from_raw_s']}s, raw {d['raw_s']}s)")
    fp = R["floor_pauses"]
    p(f"floor pauses (n={fp['n']}) median raw {fp['raw']['median']} / Leon {fp['leon']['median']} / AI {fp['ai']['median']}; "
      f">1s raw {fp['raw']['n_gt_1s']} Leon {fp['leon']['n_gt_1s']} AI {fp['ai']['n_gt_1s']}; paired MAE {fp['paired_mae_s']}s")
    p("by category:", json.dumps(R["by_category"], ensure_ascii=False))
    ij = R["interjections"]
    p(f"interjections: {ij['n_candidates']} candidates; GT moved {ij['gt_moved']}, AI moved {ij['ai_moved']}, both {ij['both_moved']}, "
      f"sign agree {ij['sign_agreement']}, median |Δ err| {ij['median_abs_delta_error_s']}; confusion {ij['confusion_gt_rows_ai_cols']}")
    p(f"false deletions total {R['false_deletion_total_s']}s; top:")
    for x in R["false_deletions_top"][:8]:
        p(f"   {x['track']} {x['raw'][0]:.2f}-{x['raw'][1]:.2f} {x['dur']}s {x['first_token']} 「{x['text'][:30]}」 {x['category']} {x['op']}")
    p("missed removals top:")
    for x in R["missed_removals_top"][:8]:
        p(f"   {x['track']} {x['raw'][0]:.2f}-{x['raw'][1]:.2f} {x['dur']}s {x['first_token']} 「{x['text'][:30]}」")
    for w in R["warnings"][:5]:
        p("   warn:", w)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ops", required=True)
    ap.add_argument("--gt", default=os.path.join(HERE, "..", "s4_alignment", "out", "ep001_alignment.json"))
    ap.add_argument("--tokens", default=os.path.join(HERE, "out", "ep001_tokens.json"))
    ap.add_argument("--tol", type=float, default=0.10)
    ap.add_argument("--event-tol", type=float, default=0.30)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json")
    ap.add_argument("--min-raw", type=float, default=None, help="score only raw time >= this (s)")
    ap.add_argument("--max-raw", type=float, default=None, help="score only raw time < this (s)")
    a = ap.parse_args()
    ops = json.load(open(a.ops, encoding="utf-8"))
    R = score(ops, a.gt, a.tokens, a.tol, a.event_tol, a.top, a.min_raw, a.max_raw)
    print_report(R, os.path.basename(a.ops))
    if a.json:
        json.dump(R, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.exit(main())
