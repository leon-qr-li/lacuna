"""Build the two sanity inputs for score.py.

  (a) oracle  : ops derived from Leon's real edit (S4 ground truth) -> should score ~perfect
  (b) baseline: tighten every floor pause (neither host speaking) > 0.8 s to 0.4 s, nothing else

Usage: python make_sanity_ops.py --out-dir out/sanity
"""
import argparse
import json
import os

import numpy as np

import score as S

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default=os.path.join(HERE, "..", "s4_alignment", "out", "ep001_alignment.json"))
    ap.add_argument("--tokens", default=os.path.join(HERE, "out", "ep001_tokens.json"))
    ap.add_argument("--out-dir", default=os.path.join(HERE, "out", "sanity"))
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    tok = json.load(open(a.tokens, encoding="utf-8"))
    n = S.fr(4500)
    tracks = {k: S.Track(k, tok["tracks"][k], n) for k in S.NAMES}
    gtd, gt_rem, _, segs = S.load_gt(a.gt, n)

    # (a) oracle
    ops = []
    for tag, nm in S.NAMES.items():
        for x, y in gtd["removed_raw"][nm]:
            spf = tracks[tag].speech[S.fr(x):S.fr(y)].mean() if y > x else 0
            cat = "pause" if spf < 0.1 else ("disfluency" if y - x < 1.0 else "content")
            ops.append({"id": f"gt{len(ops):04d}", "op": "cut", "track": tag, "from": round(x, 3), "to": round(y, 3),
                        "category": cat, "reason": "S4 removed_raw", "confidence": 1.0})
    for m in gtd["muted_track_spans"]:
        if m["same_offset_heard_both_sides"]:
            ops.append({"id": f"gt{len(ops):04d}", "op": "cut", "track": "L" if m["track"] == "Leon" else "P",
                        "from": m["raw"][0], "to": m["raw"][1], "category": "single_track_noise",
                        "reason": "S4 verified muted span", "confidence": 1.0})
    for u in S.interjections(tracks, n):
        g, d = S.gt_interjection_state(u, gt_rem, segs, tracks)
        if g == "moved":
            ops.append({"id": f"gt{len(ops):04d}", "op": "slip", "track": u["track"], "from": u["first"],
                        "to": u["last"], "delta_s": round(d, 2), "category": "interjection_move",
                        "reason": "S4 relative offset change", "confidence": 1.0})
    json.dump({"episode": "EP001", "model": "oracle-from-S4", "ops": ops},
              open(os.path.join(a.out_dir, "oracle_ops.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    # (b) baseline
    both_sil = ~(tracks["L"].speech | tracks["P"].speech)
    ops = []
    for x, y in S.runs(both_sil):
        if x == 0 or y >= n - 10 or (y - x) * S.HOP <= 0.8:
            continue
        ops.append({"id": f"b{len(ops):04d}", "op": "tighten_pause", "track": "both", "at": round((x + y) / 2 * S.HOP, 2),
                    "target_s": 0.4, "category": "pause", "reason": f"floor pause {(y - x) * S.HOP:.2f}s > 0.8s",
                    "confidence": 0.5})
    json.dump({"episode": "EP001", "model": "baseline-tighten-0.8-to-0.4", "ops": ops},
              open(os.path.join(a.out_dir, "baseline_ops.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("wrote", a.out_dir)


if __name__ == "__main__":
    main()
