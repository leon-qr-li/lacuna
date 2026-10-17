"""S5 v2: derive Leon's editing statistics from the CALIBRATION half of EP001 (raw < 2200 s) only.

All inputs are filtered at load time by calib_common.load() (raw < CUT). Writes calib_rules_stats.json.
The prose rules (learned_rules_calib.txt) were written by hand from these numbers + the printed
examples (calibration half only).

Also: --slice-heldout writes out/ep001_editor_input_heldout.md mechanically (keeps the header and
format/overview sections, then only overlap rows / transcript lines whose raw start >= CUT); it never
parses or prints the held-out content.
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import re
from collections import Counter

import numpy as np

from calib_common import CUT, HOP, HERE, NAMES, Calib, fr

FILL = set("嗯呃啊哦额唉诶哎呀嘛噢喔欸呐")
BC = set("嗯对是哦啊哈好呵噢欸诶唉嘛呀") | {"ok", "yes", "yeah", "right"}


def pct(v, ps=(10, 50, 90)):
    v = np.asarray(v, float)
    if not len(v):
        return None
    d = {f"p{p}" if p != 50 else "median": round(float(np.percentile(v, p)), 2) for p in ps}
    d["n"] = int(len(v))
    d["mean"] = round(float(v.mean()), 2)
    return d


def kept(c, k, x):
    return c.removed_frac(k, x["start"], x["end"]) <= 0.5


def main_stats(c: Calib):
    T = c.toks
    S = {"scope": f"EP001 calibration half, raw 0-{CUT:.0f} s only", "minutes": round(CUT / 60, 2)}
    # ---------------- overall
    fin = sum(s["final_end"] - s["final_start"] for s in c.segs)
    raw_span = max(s["leon_src"][1] for s in c.segs)
    ov = {"final_s_from_calib_raw": round(fin, 1), "raw_s": round(raw_span, 1),
          "final_over_raw": round(fin / raw_span, 3)}
    for k, nm in NAMES.items():
        rem = c.rem[k].sum() * HOP
        sp = c.speech[k].sum() * HOP
        sprem = (c.rem[k] & c.speech[k]).sum() * HOP
        ntok = len(T[k])
        nrem = sum(not kept(c, k, x) for x in T[k])
        ov[nm] = {"removed_s": round(rem, 1), "removed_s_per_min": round(rem / (CUT / 60), 2),
                  "speech_s": round(sp, 1), "speech_removed_s": round(sprem, 1),
                  "speech_removed_frac": round(sprem / sp, 3),
                  "speech_removed_s_per_min": round(sprem / (CUT / 60), 2),
                  "non_speech_removed_s": round(rem - sprem, 1),
                  "tokens": ntok, "tokens_removed": nrem, "tokens_removed_frac": round(nrem / ntok, 3),
                  "muted_in_place_verified_s": round(c.mutemask[k].sum() * HOP, 1)}
    ov["removed_on_both_tracks_s"] = round((c.cutmask["L"] & c.cutmask["P"]).sum() * HOP, 1)
    S["overall"] = ov

    # ---------------- pauses (final timeline)
    uidx = {}
    for k in NAMES:
        m = {}
        for j, u in enumerate(c.utts[k]):
            for t in range(u["tok"][0], u["tok"][1]):
                m[t] = j
        uidx[k] = m
    ev = []
    for k in NAMES:
        for i, x in enumerate(T[k]):
            if not kept(c, k, x):
                continue
            a = c.to_final(k, x["start"])
            b = c.to_final(k, x["end"] - 0.005)
            if a is None or b is None or b < a:
                continue
            ev.append((a, b + 0.005, k, i))
    ev.sort()
    gaps, ce, pv = [], -1, None
    for a, b, k, i in ev:
        if pv is not None and a - ce >= 0.05:
            gaps.append((ce, a, pv, (k, i)))
        if b > ce:
            ce, pv = b, (k, i)

    def isq(k, i):
        tail = "".join(x["t"] for x in T[k][max(0, i - 5):i + 1])
        return T[k][i]["t"] in "吗呢么嘛" or any(w in tail for w in ("什么", "怎么", "哪", "谁", "多少", "是不是", "有没有"))

    rows = []
    for a, b, (pk, pi), (nk, ni) in gaps:
        if not (pk != nk or uidx[pk].get(pi) != uidx[nk].get(ni)):
            continue  # intra-utterance
        pr, nr = T[pk][pi]["end"], T[nk][ni]["start"]
        adj = nr > pr and not (c.speech["L"][fr(pr) + 1:fr(nr) - 1].any() or c.speech["P"][fr(pr) + 1:fr(nr) - 1].any())
        rows.append(dict(f=b - a, turn=pk != nk, q=pk != nk and isq(pk, pi),
                         laugh=any(ch in T[pk][pi]["t"] + T[nk][ni]["t"] for ch in "哈呵"), junction=not adj))
    P = {"definition": "gaps between consecutive kept speech in the FINAL timeline (union of both tracks), "
                       "at utterance boundaries or speaker changes",
         "all": pct([r["f"] for r in rows]),
         "turn_change": pct([r["f"] for r in rows if r["turn"]]),
         "same_speaker": pct([r["f"] for r in rows if not r["turn"]]),
         "after_question_turn_change": pct([r["f"] for r in rows if r["q"]]),
         "around_laughter_token": pct([r["f"] for r in rows if r["laugh"]]),
         "at_edit_junction": pct([r["f"] for r in rows if r["junction"]]),
         "final_pauses_over_1s": int(sum(r["f"] > 1 for r in rows))}
    # raw -> final mapping for raw union gaps whose bounding tokens are both kept
    allt = sorted([(x["start"], x["end"], k, i) for k in NAMES for i, x in enumerate(T[k])])
    rg, ce, pv = [], -1, None
    for s, e, k, i in allt:
        if pv and s - ce >= 0.3:
            rg.append((ce, s, pv, (k, i)))
        if e > ce:
            ce, pv = e, (k, i)
    mp = []
    for a, b, (pk, pi), (nk, ni) in rg:
        if not (kept(c, pk, T[pk][pi]) and kept(c, nk, T[nk][ni])):
            continue
        fa, fb = c.to_final(pk, T[pk][pi]["end"] - 0.005), c.to_final(nk, T[nk][ni]["start"])
        if fa is None or fb is None:
            continue
        mp.append((b - a, fb - fa, pk, nk))
    tab = []
    for lo, hi in [(0.3, 0.5), (0.5, 0.8), (0.8, 1.2), (1.2, 2), (2, 99)]:
        for lab, cond in [("L->P", lambda p, n: p == "L" and n == "P"), ("P->L", lambda p, n: p == "P" and n == "L"),
                          ("same_speaker", lambda p, n: p == n)]:
            s = [m for m in mp if lo <= m[0] < hi and cond(m[2], m[3])]
            if s:
                f = np.array([m[1] for m in s]); r = np.array([m[0] for m in s])
                tab.append({"raw_range": [lo, hi], "ctx": lab, "n": len(s),
                            "final_median": round(float(np.median(f)), 2),
                            "final_p10": round(float(np.percentile(f, 10)), 2),
                            "final_p90": round(float(np.percentile(f, 90)), 2),
                            "untouched_frac": round(float(np.mean(np.abs(f - r) < 0.05)), 2)})
    P["raw_gap_to_final"] = tab
    P["n_raw_gaps_ge_0.3"] = len(rg)
    P["n_raw_gaps_both_sides_kept"] = len(mp)
    S["pauses"] = P

    # ---------------- removed speech runs
    runs = []
    for k in NAMES:
        rm = [not kept(c, k, x) for x in T[k]]
        i, n = 0, len(T[k])
        while i < n:
            if rm[i]:
                j = i
                while j + 1 < n and rm[j + 1] and T[k][j + 1]["start"] - T[k][j]["end"] < 1.5:
                    j += 1
                t = "".join(x["t"] for x in T[k][i:j + 1])
                core = "".join(ch for ch in t if ch not in FILL)
                nxt = "".join(x["t"] for x in T[k][j + 1:j + 12])
                dur = T[k][j]["end"] - T[k][i]["start"]
                if not core:
                    cl = "filler"
                elif len(core) <= 8 and nxt.startswith(core[:2]) or len(core) <= 4 and core[:2] in nxt[:6]:
                    cl = "restart"
                elif dur >= 2.0 or j - i + 1 >= 10:
                    cl = "content"
                else:
                    cl = "fragment"
                if T[k][j]["end"] < CUT - 2:  # drop a run clipped by the boundary
                    runs.append(dict(track=k, id0=T[k][i]["id"], id1=T[k][j]["id"], start=round(T[k][i]["start"], 2),
                                     dur=round(dur, 2), n=j - i + 1, cls=cl, text=t))
                i = j + 1
            else:
                i += 1
    R = {}
    for k, nm in NAMES.items():
        o = [r for r in runs if r["track"] == k]
        d = {"runs": len(o), "runs_per_min": round(len(o) / (CUT / 60), 2)}
        for cl in ("filler", "restart", "fragment", "content"):
            s = [r for r in o if r["cls"] == cl]
            d[cl] = {"n": len(s), "s": round(sum(r["dur"] for r in s), 1)}
        d["runs_ge_2s_dur"] = pct([r["dur"] for r in o if r["dur"] >= 2], (10, 25, 50, 75, 90))
        d["runs_ge_2s_total_s"] = round(sum(r["dur"] for r in o if r["dur"] >= 2), 1)
        d["max_run_s"] = max(r["dur"] for r in o)
        rm = [not kept(c, k, x) for x in T[k]]
        f = [i for i, x in enumerate(T[k]) if x["t"] in FILL]
        d["filler_tokens"] = {"n": len(f), "removed": sum(rm[i] for i in f)}
        fu = [u for u in c.utts[k] if u.get("n") and all(T[k][t]["t"] in FILL for t in range(*u["tok"]))]
        d["filler_only_utterances"] = {"n": len(fu), "removed": int(sum(np.mean(rm[u["tok"][0]:u["tok"][1]]) > 0.5 for u in fu))}
        reps = []
        t = T[k]
        for i in range(len(t) - 1):
            if t[i]["t"] in FILL:
                continue
            if t[i + 1]["t"] == t[i]["t"] and t[i + 1]["start"] - t[i]["end"] < 0.8:
                reps.append((i, 1))
            elif i + 3 < len(t) and t[i + 2]["t"] == t[i]["t"] and t[i + 3]["t"] == t[i + 1]["t"] and t[i + 1]["t"] not in FILL:
                reps.append((i, 2))
        d["immediate_repeats"] = {"n": len(reps), "any_part_removed": sum(any(rm[i:i + 2 * m]) for i, m in reps)}
        js = [i for i in range(len(t) - 1) if t[i]["t"] == "就" and t[i + 1]["t"] == "是"]
        d["jiushi"] = {"n": len(js), "removed": sum(rm[i] and rm[i + 1] for i in js)}
        R[nm] = d
    S["removed_speech_runs"] = R

    # ---------------- overlaps / backchannels / noise
    idx = {k: {x["id"]: i for i, x in enumerate(T[k])} for k in NAMES}
    O = {"n": len(c.overlaps), "total_s": round(sum(o["dur"] for o in c.overlaps), 1)}
    only_l = only_p = both = 0
    for o in c.overlaps:
        lr = c.removed_frac("L", o["start"], o["end"]) > 0.5
        pr = c.removed_frac("P", o["start"], o["end"]) > 0.5
        only_l += lr and not pr
        only_p += pr and not lr
        both += lr and pr
    O.update(leon_side_cut_only=only_l, pei_side_cut_only=only_p, both_cut=both,
             neither_cut=len(c.overlaps) - only_l - only_p - both)
    S["overlaps"] = O

    def shift(k, r):
        o = "P" if k == "L" else "L"
        fk, fo = c.to_final(k, r), c.to_final(o, r)
        return None if fk is None or fo is None else (fk - r) - (fo - r)

    B = {}
    for k, nm in NAMES.items():
        o = "P" if k == "L" else "L"
        out = []
        for u in c.utts[k]:
            if not u.get("n"):
                continue
            tk = T[k][u["tok"][0]:u["tok"][1]]
            if len(tk) > 3 or not all(x["t"].lower() in BC for x in tk):
                continue
            a, b = u["start"], u["end"]
            if not (c.speech[o][max(0, fr(a - 1.5)):fr(a)].any() and c.speech[o][fr(b):fr(b + 1.5)].any()):
                continue
            out.append(dict(rem=c.removed_frac(k, a, b), sh=shift(k, (a + b) / 2), rawov=c.speech[o][fr(a):fr(b)].mean(),
                            other_cut=c.removed_frac(o, a - 1, b + 1)))
        kp = [x for x in out if x["rem"] < 0.5]
        sh = [x["sh"] for x in kp if x["sh"] is not None]
        B[nm] = {"backchannels_inside_other_turn": len(out), "removed": len(out) - len(kp),
                 "removed_with_other_track_cut_ge_0.7_within_1s": sum(x["rem"] >= 0.5 and x["other_cut"] >= 0.7 for x in out),
                 "kept_overlapping_other_raw": int(sum(x["rawov"] > 0.3 for x in kp)),
                 "kept_rel_shift_abs": pct(np.abs(sh), (25, 50, 75, 90)),
                 "kept_shift_ge_0.3_earlier": int(sum(s <= -0.3 for s in sh)),
                 "kept_shift_ge_0.3_later": int(sum(s >= 0.3 for s in sh))}
    S["backchannels"] = B
    d = np.array([s["offset_pei"] - s["offset_leon"] for s in c.segs])
    w = np.array([s["final_end"] - s["final_start"] for s in c.segs])
    S["track_offset"] = {
        "definition": "pei_minus_leon offset change vs raw, weighted by final seconds; >0 = Pei plays earlier relative to Leon",
        "final_s_in_sync": round(float(w[np.abs(d) < 0.05].sum()), 1),
        "final_s_pei_earlier": round(float(w[d >= 0.05].sum()), 1),
        "final_s_pei_later": round(float(w[d <= -0.05].sum()), 1),
        "abs_offset_final_s": {f"{lo}-{hi}": round(float(w[(np.abs(d) >= lo) & (np.abs(d) < hi)].sum()), 1)
                               for lo, hi in [(0.05, 0.3), (0.3, 0.6), (0.6, 1), (1, 99)]}}
    N = {}
    for k, nm in NAMES.items():
        o = "P" if k == "L" else "L"
        S_ = [s for s in c.sounds if s["track"] == k]
        under = [s for s in S_ if c.speech[o][fr(s["start"]):fr(s["end"])].mean() > 0.5]
        quiet = [s for s in S_ if c.speech[o][fr(s["start"]):fr(s["end"])].mean() <= 0.1]
        N[nm] = {"snd_candidates": len(S_),
                 "under_other_speech": len(under),
                 "under_other_removed": sum(c.removed_frac(k, s["start"], s["end"]) > 0.5 for s in under),
                 "in_floor_silence": len(quiet),
                 "in_floor_silence_removed": sum(c.removed_frac(k, s["start"], s["end"]) > 0.5 for s in quiet),
                 "verified_mutes": sum(1 for m in c.muted if m["track"] == k and m["verified"])}
    S["single_track_noise"] = N
    return S, runs


def slice_heldout(src, dst):
    """Mechanical slice: header/format/overview kept verbatim; overlap rows and transcript lines kept
    only if their leading raw start time >= CUT. Lines are classified by regex on their prefix only."""
    lines = open(src, encoding="utf-8").read().split("\n")
    out, sect = [], "head"
    ov_re = re.compile(r"^- (\d+\.\d+)-\d+\.\d+ ")
    tr_re = re.compile(r"^[LP] (\d+\.\d+)-")
    gap_re = re.compile(r"^== .*\(raw (\d+\.\d+)-")
    min_re = re.compile(r"^--- (\d+):(\d\d) ---")
    n_kept = Counter()
    for ln in lines:
        if ln.startswith("### 重叠表"):
            sect = "ov"
            out.append(ln)
            continue
        if ln.startswith("## 全文"):
            sect = "tr"
            out.append(ln)
            continue
        if sect == "head":
            out.append(ln)
            continue
        if sect == "ov":
            m = ov_re.match(ln)
            if m:
                if float(m.group(1)) >= CUT:
                    out.append(ln); n_kept["overlap"] += 1
            elif not ln.startswith("- "):
                out.append(ln)  # table legend / blank lines
            continue
        # transcript
        if not ln.strip():
            if out and out[-1].strip():
                out.append(ln)
            continue
        m = tr_re.match(ln) or gap_re.match(ln)
        if m:
            if float(m.group(1)) >= CUT:
                out.append(ln); n_kept["line"] += 1
            continue
        m = min_re.match(ln)
        if m:
            if int(m.group(1)) * 60 + int(m.group(2)) >= CUT:
                out.append(ln)
            continue
        raise SystemExit(f"unclassified transcript line (prefix): {ln[:12]!r}")
    # note in header
    for i, ln in enumerate(out):
        if ln.startswith("## 格式说明"):
            out.insert(i, f"> HELD-OUT SLICE: only overlaps / transcript lines with raw start >= {CUT:.0f} s "
                          f"(EP001 second half). The overview numbers below describe the whole episode.\n")
            break
    open(dst, "w", encoding="utf-8").write("\n".join(out))
    return dict(n_kept)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice-heldout", action="store_true")
    ap.add_argument("--dump-runs", help="write calibration removed-run list (json) here")
    a = ap.parse_args()
    if a.slice_heldout:
        print(slice_heldout(os.path.join(HERE, "out", "ep001_editor_input.md"),
                            os.path.join(HERE, "out", "ep001_editor_input_heldout.md")))
    else:
        c = Calib()
        S, runs = main_stats(c)
        json.dump(S, open(os.path.join(HERE, "calib_rules_stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if a.dump_runs:
            json.dump(runs, open(a.dump_runs, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        print(json.dumps(S, ensure_ascii=False, indent=1))
