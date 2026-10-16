"""Compare ASR engine outputs for S2 (no human reference available).

Evidence produced:
  1. per-engine stats: chars, filler counts, immediate repetitions, RTF, peak RSS
  2. pairwise char disagreement (normalized edit distance) between engines
  3. 60 s sub-excerpt: disfluency recall against a consensus reference (reference_leon_60s.json)
  4. timestamp vs signal energy: onset/offset error distributions + valley test vs random baseline
  5. silence / bleed behaviour on the Pei track (VAD vs no VAD)
  6. side-by-side snippets

Usage:
  python compare.py --runs OUT_DIR --audio-dir AUDIO_DIR [--ref reference_leon_60s.json] > tables.md
Writes OUT_DIR/summary.json as well.
"""
import argparse
import glob
import json
import os
import re
import unicodedata

import numpy as np

from common import SR, load_wav

FILLERS = {
    "嗯": "嗯恩摁唔呣", "呃": "呃额厄", "啊": "啊阿", "哦": "哦噢喔", "诶": "诶欸",
    "那个": None, "就是": None, "然后": None,
}
PUNCT_RE = re.compile(r"[\s　-〿＀-／：-＠［-｀｛-･,.!?;:'\"()\[\]<>\-]+")


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).lower().replace("@@", "")
    return PUNCT_RE.sub("", t)


# Typical Whisper zh hallucinations (subtitle credits / outro boilerplate learned from web video)
HALLUCINATION_RE = re.compile(r"请不吝|点赞|订阅|转发|打赏|明镜|栏目|字幕|谢谢观看|感谢观看|下期再见|amara")


def is_cjk(c):
    return "一" <= c <= "鿿"


def count_fillers(t: str) -> dict:
    out = {}
    for k, variants in FILLERS.items():
        if variants is None:
            out[k] = t.count(k)
        else:
            # 啊/阿 as a standalone filler is ambiguous inside words (阿姨, 迈阿密); only count 啊 for 啊
            vs = "啊" if k == "啊" else variants
            out[k] = sum(t.count(v) for v in vs)
    return out


def repetitions(t: str, max_n: int = 4) -> list[str]:
    """Immediate repeats of 1..max_n CJK chars (e.g. 不是不是, 那那, 这个这个)."""
    found = []
    i = 0
    while i < len(t):
        hit = None
        for n in range(max_n, 0, -1):
            a, b = t[i:i + n], t[i + n:i + 2 * n]
            if len(a) == n and a == b and all(is_cjk(c) for c in a):
                # skip common lexical reduplications
                if n == 1 and a in "哈对嗯啊谢看想试聊等走说":
                    continue
                hit = a + a
                break
        if hit:
            found.append(hit)
            i += len(hit)
        else:
            i += 1
    return found


def edit_distance(a: str, b: str) -> int:
    from rapidfuzz.distance import Levenshtein
    return Levenshtein.distance(a, b)


def toks_in(run, t0, t1):
    return [t for s in run["segments"] for t in s.get("tokens", []) if t0 <= t["start"] < t1]


def text_in(run, t0, t1):
    tk = toks_in(run, t0, t1)
    if tk:
        return "".join(t["t"] for t in tk)
    # engines without token timestamps: whole segments overlapping
    return "".join(s["text"] for s in run["segments"] if s["start"] < t1 and s["end"] > t0)


# ---------------------------------------------------------------- energy analysis
def energy_db(x, hop=0.01, win=0.02):
    h, w = int(hop * SR), int(win * SR)
    n = 1 + max(0, (len(x) - w) // h)
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    fr = x[idx]
    return 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)


def onsets_offsets(e, floor, hop=0.01, min_sil=0.2, hi=15, lo=8):
    """Energy-based speech onsets/offsets with hysteresis.  Returns times in s."""
    speech = np.zeros(len(e), bool)
    on = False
    for i, v in enumerate(e):
        if not on and v > floor + hi:
            on = True
        elif on and v < floor + lo:
            on = False
        speech[i] = on
    # extend speech backwards/forwards to the lo threshold (true rise start / decay end)
    onsets, offsets = [], []
    i, n = 0, len(e)
    sil_frames = int(min_sil / hop)
    while i < n:
        if speech[i] and (i == 0 or not speech[i - 1]):
            j = i
            while j > 0 and e[j - 1] > floor + lo:
                j -= 1
            # require preceding silence >= min_sil
            if j >= sil_frames and not speech[j - sil_frames:j].any():
                onsets.append(j * hop)
        if speech[i] and (i + 1 == n or not speech[i + 1]):
            j = i
            while j + 1 < n and e[j + 1] > floor + lo:
                j += 1
            if j + 1 + sil_frames <= n and not speech[j + 1:j + 1 + sil_frames].any():
                offsets.append((j + 1) * hop)
        i += 1
    return np.array(onsets), np.array(offsets), speech


def boundary_stats(run, onsets, offsets, e, floor, hop=0.01, search=0.5):
    starts = np.array([t["start"] for s in run["segments"] for t in s.get("tokens", [])])
    ends = np.array([t["end"] for s in run["segments"] for t in s.get("tokens", []) if t.get("end") is not None])
    res = {}
    if len(starts) == 0:
        return None
    def nearest(ref, cand):
        errs = []
        for r in ref:
            d = cand - r
            k = np.argmin(np.abs(d))
            if abs(d[k]) <= search:
                errs.append(d[k])
        return np.array(errs)
    on_err = nearest(onsets, starts)
    off_err = nearest(offsets, ends)
    def summ(x):
        if len(x) == 0:
            return None
        ax = np.abs(x) * 1000
        return {"n": int(len(x)), "median_signed_ms": round(float(np.median(x) * 1000), 0),
                "median_abs_ms": round(float(np.median(ax)), 0), "p90_abs_ms": round(float(np.percentile(ax, 90)), 0),
                "within_50ms": round(float((ax <= 50).mean()), 2), "within_100ms": round(float((ax <= 100).mean()), 2)}
    res["onset_err"] = summ(on_err)    # +: token start later than energy onset (cut would clip the head)
    res["offset_err"] = summ(off_err)  # -: token end earlier than energy offset (cut would clip the tail)
    res["onset_late_gt30ms"] = round(float((on_err > 0.03).mean()), 2) if len(on_err) else None
    res["offset_early_gt30ms"] = round(float((off_err < -0.03).mean()), 2) if len(off_err) else None
    res["coverage_onsets"] = round(len(on_err) / max(1, len(onsets)), 2)

    # valley test on ALL token starts: energy at boundary relative to local max within +-150 ms
    def rel_db(t):
        i = int(round(t / hop))
        if i < 15 or i >= len(e) - 15:
            return None
        return float(e[i] - e[i - 15:i + 16].max())
    rd = np.array([v for v in (rel_db(t) for t in starts) if v is not None])
    res["start_rel_db_median"] = round(float(np.median(rd)), 1)
    res["start_in_valley_frac"] = round(float((rd <= -10).mean()), 2)  # >=10 dB below local peak
    return res


def random_valley_baseline(e, speech, hop=0.01, n=3000, seed=0):
    rng = np.random.default_rng(seed)
    idx = np.nonzero(speech)[0]
    idx = idx[(idx > 15) & (idx < len(e) - 16)]
    pick = rng.choice(idx, size=min(n, len(idx)), replace=False)
    rd = np.array([e[i] - e[i - 15:i + 16].max() for i in pick])
    return {"start_rel_db_median": round(float(np.median(rd)), 1), "start_in_valley_frac": round(float((rd <= -10).mean()), 2)}


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--audio-dir", required=True)
    ap.add_argument("--ref", default=os.path.join(os.path.dirname(__file__), "reference_leon_60s.json"))
    a = ap.parse_args()

    runs = {}
    for p in sorted(glob.glob(os.path.join(a.runs, "*.json"))):
        if os.path.basename(p) == "summary.json":
            continue
        d = json.load(open(p, encoding="utf-8"))
        if "engine" not in d:
            continue
        track = "Leon" if "Leon" in d["audio"] else "Pei"
        runs[(os.path.basename(p)[:-5].replace("_" + track, ""), track)] = d
    summary = {"stats": {}, "pairwise": {}, "timestamps": {}, "silence": {}, "ref": {}}

    # 1. stats
    print("## 1. Per-engine stats (5-min excerpts, 900-1200 s)\n")
    print("| run | track | chars | 嗯 | 呃 | 啊 | 哦 | 那个 | 就是 | 然后 | imm. repeats | halluc. phrases | RTF (4 thr CPU) | peak RSS MB | load s |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for (name, tr), d in sorted(runs.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        t = norm(d["text"])
        f = count_fillers(t)
        reps = repetitions(t)
        hal = [s_["text"] for s_ in d["segments"] if HALLUCINATION_RE.search(s_["text"].lower())]
        summary["stats"][f"{name}|{tr}"] = {"chars": len(t), "fillers": f, "repeats": reps, "rtf": d["rtf"],
                                            "peak_rss_mb": d["peak_rss_mb"], "load_s": d["load_s"], "hallucinations": hal}
        print(f"| {name} | {tr} | {len(t)} | {f['嗯']} | {f['呃']} | {f['啊']} | {f['哦']} | {f['那个']} | {f['就是']} | "
              f"{f['然后']} | {len(reps)} | {len(hal)} | {d['rtf']:.3f} | {d['peak_rss_mb']:.0f} | {d['load_s']:.1f} |")

    # SenseVoice event / emotion tags
    from collections import Counter
    for (name, tr), d in sorted(runs.items()):
        if name.startswith("sensevoice"):
            ev = Counter(s_.get("event") for s_ in d["segments"])
            emo = Counter(s_.get("emotion") for s_ in d["segments"])
            summary["stats"][f"{name}|{tr}"]["events"] = dict(ev)
            print(f"\n{name} {tr}: event tags {dict(ev)}; emotion tags {dict(emo)}")

    # repeats detail (Leon)
    print("\n### Immediate repetitions found (Leon)\n")
    for (name, tr), d in sorted(runs.items()):
        if tr == "Leon":
            print(f"- **{name}**: {' '.join(repetitions(norm(d['text']))) or '(none)'}")

    # 2. pairwise
    print("\n## 2. Pairwise normalized char edit distance (Leon, VAD runs)\n")
    keys = [k for k in sorted(runs) if k[1] == "Leon" and "novad" not in k[0]]
    names = [k[0] for k in keys]
    print("| | " + " | ".join(names) + " |")
    print("|---" * (len(names) + 1) + "|")
    texts = {k: norm(runs[k]["text"]) for k in keys}
    for k1 in keys:
        row = []
        for k2 in keys:
            if k1 == k2:
                row.append("–")
                continue
            dd = edit_distance(texts[k1], texts[k2]) / max(len(texts[k1]), len(texts[k2]))
            summary["pairwise"][f"{k1[0]}~{k2[0]}"] = round(dd, 3)
            row.append(f"{dd:.2f}")
        print(f"| {k1[0]} | " + " | ".join(row) + " |")

    # 3. reference
    if os.path.exists(a.ref):
        ref = json.load(open(a.ref, encoding="utf-8"))
        t0, t1 = ref["window"]
        print(f"\n## 3. Disfluency recall on Leon {t0}-{t1} s vs consensus reference ({len(ref['items'])} items)\n")
        print("| run | " + " | ".join(f"{it['id']}" for it in ref["items"]) + " | recall | CER vs ref |")
        print("|---" * (len(ref["items"]) + 3) + "|")
        rtext = norm(ref["text"])
        for k in keys:
            d = runs[k]
            hits = []
            for it in ref["items"]:
                w = text_in(d, it["t"] - it.get("tol", 1.0), it["t"] + it.get("tol", 1.0))
                hits.append(norm(it["match"]) in norm(w))
            seg = norm(text_in(d, t0, t1))
            cer = edit_distance(seg, rtext) / len(rtext)
            summary["ref"][k[0]] = {"hits": hits, "recall": round(sum(hits) / len(hits), 2), "cer": round(cer, 3)}
            print(f"| {k[0]} | " + " | ".join("✓" if h else "✗" for h in hits) + f" | {sum(hits)}/{len(hits)} | {cer:.2f} |")
        print("\nItems: " + "; ".join(f"{it['id']}={it['type']}「{it['match']}」@{it['t']}s" for it in ref["items"]))

    # 4. timestamps vs energy (Leon)
    print("\n## 4. Timestamp boundaries vs signal energy (Leon track, 10 ms frames)\n")
    x = load_wav(os.path.join(a.audio_dir, "Leon_900_1200.wav"))
    e = energy_db(x)
    floor = float(np.percentile(e, 10))
    on, off, speech = onsets_offsets(e, floor)
    base = random_valley_baseline(e, speech)
    print(f"noise floor (p10) {floor:.1f} dB; energy onsets after >=200 ms silence: {len(on)}, offsets: {len(off)}\n")
    print("Onset err = token start − energy onset (+ = late → cut would clip word head). "
          "Offset err = token end − energy offset (− = early → clips tail).\n")
    print("| run | onsets matched | onset med signed ms | onset med abs ms | onset p90 abs ms | onset ≤50ms | late>30ms | "
          "offset med signed ms | offset p90 abs ms | early>30ms | start rel dB (med) | start in valley |")
    print("|---" * 12 + "|")
    for k in keys:
        st = boundary_stats(runs[k], on, off, e, floor)
        if not st:
            continue
        summary["timestamps"][k[0]] = st
        o, f = st["onset_err"] or {}, st["offset_err"] or {}
        print(f"| {k[0]} | {st['coverage_onsets']:.0%} | {o.get('median_signed_ms')} | {o.get('median_abs_ms')} | "
              f"{o.get('p90_abs_ms')} | {o.get('within_50ms')} | {st['onset_late_gt30ms']} | {f.get('median_signed_ms')} | "
              f"{f.get('p90_abs_ms')} | {st['offset_early_gt30ms']} | {st['start_rel_db_median']} | {st['start_in_valley_frac']} |")
    print(f"| *random times in speech (baseline)* | | | | | | | | | | {base['start_rel_db_median']} | {base['start_in_valley_frac']} |")
    summary["timestamps"]["_baseline_random"] = base

    # 5. silence / bleed on Pei
    print("\n## 5. Pei track: output in low-energy regions (silence / bleed), VAD vs no VAD\n")
    xp = load_wav(os.path.join(a.audio_dir, "Pei_900_1200.wav"))
    ep = energy_db(xp)
    fp = float(np.percentile(ep, 10))
    _, _, sp = onsets_offsets(ep, fp)
    leon_text = {k[0]: norm(runs[k]["text"]) for k in runs if k[1] == "Leon"}
    print(f"Pei noise floor {fp:.1f} dB; frames classed as Pei speech/energy: {sp.mean():.0%}\n")
    print("| run | chars | chars timed in low-energy frames | segs with compression_ratio>2.4 | max identical segment (≥4 chars) | "
          "chars also in Leon's transcript (≥4-gram, bleed proxy) |")
    print("|---|---|---|---|---|---|")
    for (name, tr), d in sorted(runs.items()):
        if tr != "Pei":
            continue
        t = norm(d["text"])
        low = 0
        for s in d["segments"]:
            for tk in s.get("tokens", []):
                i0, i1 = int(tk["start"] / 0.01), max(int(tk["start"] / 0.01) + 1, int((tk["end"] or tk["start"]) / 0.01))
                if not sp[max(0, i0 - 10):i1 + 10].any():
                    low += len(norm(tk["t"]))
        cr = sum(1 for s in d["segments"] if s.get("compression_ratio", 0) > 2.4)
        segtexts = [norm(s["text"]) for s in d["segments"] if len(norm(s["text"])) >= 4]
        maxrep = max((segtexts.count(s) for s in set(segtexts)), default=0)
        lt = leon_text.get(name, "")
        covered = np.zeros(len(t), bool)
        for i in range(len(t) - 3):
            if t[i:i + 4] in lt:
                covered[i:i + 4] = True
        summary["silence"][name] = {"chars": len(t), "low_energy_chars": low, "high_cr_segs": cr,
                                    "max_identical_segment_repeats": maxrep, "chars_in_leon": int(covered.sum())}
        print(f"| {name} | {len(t)} | {low} | {cr} | {maxrep} | {int(covered.sum())} |")

    # 6. side-by-side snippets
    print("\n## 6. Side-by-side snippets (Leon; token text with first-token start time)\n")
    for w0, w1 in [(11.0, 24.0), (264.0, 282.5), (286.5, 293.0), (298.5, 300.0)]:
        print(f"**{w0:.0f}–{w1:.0f} s**\n")
        print("| run | text |\n|---|---|")
        for k in keys:
            tk = toks_in(runs[k], w0, w1)
            txt = "".join(t['t'].replace('@@', '') for t in tk) if tk else text_in(runs[k], w0, w1)
            print(f"| {k[0]} | {txt} |")
        print()
    json.dump(summary, open(os.path.join(a.runs, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
