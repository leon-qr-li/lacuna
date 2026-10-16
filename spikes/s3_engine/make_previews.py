#!/usr/bin/env python3
"""Render short before/after WAV pairs of three engine edits on EP001's raw tracks, for Leon
to listen to. Positions are found automatically (energy + S2 ASR + S4 map) and logged to
spikes/s3_engine/out/previews.json. Audio goes only to --out (outside the repo).

  python3 spikes/s3_engine/make_previews.py --out /mnt/project-files/lacuna/previews
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lacuna_core import (CutRange, LiftRange, Previewer, Project, RenderSettings, Renderer,
                         SetRoomTone, SetTrackGain, SlipRegion, SourcePool, add_source_clip,
                         check_seams, frame_db, new_timeline, quietest_span, seams,
                         snap_cut_media)
import ep001
from run_proof import OUT, media_table

CTX = 4.5            # seconds of context either side
FRAME = 0.01


def levels(pool, mid, a_s, b_s, sr):
    return frame_db(pool.read(mid, int(a_s * sr), int(b_s * sr)), sr)


def quiet_runs(mask: np.ndarray, min_frames: int):
    runs, start = [], None
    for i, q in enumerate(np.append(mask, False)):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if i - start >= min_frames:
                runs.append((start, i))
            start = None
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    media = media_table(OUT / "media_ids.json")
    ids = {n: next(m.media_id for m in media.values() if Path(m.path) == p) for n, p in ep001.RAW.items()}
    sr = next(iter(media.values())).sample_rate
    pool = SourcePool(media)
    S = lambda s: int(round(s * sr))

    tl = new_timeline(sr, ["Leon", "Pei"])
    for n in ("Leon", "Pei"):
        tl = add_source_clip(tl, n, media[ids[n]])
    proj = Project(media, tl)
    proj.apply(SetTrackGain("Leon", 6.97))                     # Leon's +7 dB (S4)
    for n in ("Leon", "Pei"):                                  # room tone for gaps, from raw
        a, b = quietest_span(pool.read(ids[n], S(600), S(780)), sr, 1.5)
        proj.apply(SetRoomTone(n, ids[n], S(600) + a, S(600) + b))
    raw = proj.timeline

    renderer = Renderer(pool, RenderSettings(xfade_ms=16))
    pv = Previewer(renderer)
    region = (900.0, 1200.0)                                   # S2's checked excerpt
    lv = {n: levels(pool, ids[n], *region, sr) for n in ids}
    floor = {n: np.percentile(lv[n], 10) for n in ids}
    quiet = {n: lv[n] < floor[n] + 18 for n in ids}
    t_of = lambda i: region[0] + i * FRAME
    log, outputs = [], []

    def emit(name, before_tl, after_tl, b0, b1, a0, a1, info):
        rb, ra = pv.render(before_tl, S(b0), S(b1)), pv.render(after_tl, S(a0), S(a1))
        for tag, res in (("before", rb), ("after", ra)):
            path = args.out / f"{name}_{tag}.wav"
            sf.write(str(path), res.audio, sr, subtype="PCM_16")
            outputs.append(path)
        rep = check_seams(ra.audio, sr, seams(after_tl), offset=S(a0))
        info.update(name=name, before_raw_s=[round(b0, 3), round(b1, 3)],
                    preview_latency_s=round(ra.seconds, 3),
                    seams=[r.to_dict() for r in rep], clicks=sum(r.click for r in rep))
        log.append(info)

    # ASR tokens (S2 Paraformer, both tracks) mark speech even when it is soft (e.g. Pei's 嗯)
    asr = {n: json.loads((ROOT / f"spikes/s2_asr/out/paraformer_{n}.json").read_text()) for n in ids}
    spoken = {n: np.zeros(len(quiet[n]), bool) for n in ids}
    for n, doc in asr.items():
        for seg in doc["segments"]:
            for tok in seg["tokens"]:
                end = min(tok["end"], tok["start"] + 0.35)     # CIF ends of final tokens run long
                spoken[n][int(tok["start"] / FRAME):int(end / FRAME) + 1] = True
    silent = quiet["Leon"] & quiet["Pei"] & ~spoken["Leon"] & ~spoken["Pei"]

    # 1. pause tightening: longest joint pause 1-3 s (no ASR token inside), tightened to ~0.4 s
    runs = [(a, b) for a, b in quiet_runs(silent, 100) if b - a <= 300]
    print("pause candidates (s):", sorted(round((b - a) * FRAME, 2) for a, b in quiet_runs(silent, 50))[-8:])
    a, b = max(runs, key=lambda r: r[1] - r[0])
    p0, p1 = t_of(a), t_of(b)
    keep = 0.2
    c0 = snap_cut_media(pool, list(ids.values()), S(p0 + keep), sr, radius_ms=60)
    c1 = snap_cut_media(pool, list(ids.values()), S(p1 - keep), sr, radius_ms=60)
    after = CutRange(c0, c1).apply(raw)
    emit("01_pause_tighten", raw, after, p0 - CTX, p1 + CTX, p0 - CTX, p1 + CTX - (c1 - c0) / sr,
         dict(pause_raw_s=[round(p0, 3), round(p1, 3)], pause_s=round(p1 - p0, 2),
              cut_raw_s=[round(c0 / sr, 4), round(c1 / sr, 4)], new_pause_s=round(p1 - p0 - (c1 - c0) / sr, 2)))

    # 2. single-track slip: a Pei backchannel over Leon's speech, slid into the nearest
    #    following Leon pause (the closest such case in the excerpt; Leon slides 0.3-2 s)
    options = []
    for seg in asr["Pei"]["segments"]:
        if not set(seg["text"]) <= set("嗯恩") or len(seg["text"]) > 2:
            continue
        i0, i1 = int(seg["start"] / FRAME), int(seg["end"] / FRAME)
        pei_on = ~quiet["Pei"][i0:i1]
        if pei_on.sum() < 15 or (~quiet["Leon"][i0:i1]).mean() < 0.5:
            continue                                            # not a real overlap
        on = np.nonzero(pei_on)[0]
        v0, v1 = t_of(i0 + on[0]) - 0.04, t_of(i0 + on[-1] + 1) + 0.06   # voiced span + margin
        # destination: both mics quiet and no Pei token there (nothing of Pei's gets overwritten)
        dest = [(x, y) for x, y in quiet_runs(quiet["Leon"] & quiet["Pei"] & ~spoken["Pei"], 30)
                if t_of(x) > v1 and (y - x) * FRAME >= (v1 - v0) + 0.12]
        if dest:
            options.append((t_of(dest[0][0]) - v0, seg["text"], v0, v1, dest[0]))
    _, text, v0, v1, (x, y) = min(options)
    m0 = snap_cut_media(pool, [ids["Pei"]], S(v0), sr, radius_ms=30)
    m1 = snap_cut_media(pool, [ids["Pei"]], S(v1), sr, radius_ms=30)
    delta = S(t_of(x) + 0.08) - m0
    after = SlipRegion("Pei", m0, m1, delta).apply(raw)
    emit("02_interjection_slip", raw, after, v0 - CTX, v1 + CTX + 1.5, v0 - CTX, v1 + CTX + 1.5,
         dict(asr_text=text, pei_raw_s=[round(m0 / sr, 3), round(m1 / sr, 3)], candidates=len(options),
              moved_by_s=round(delta / sr, 3), leon_pause_raw_s=[round(t_of(x), 2), round(t_of(y), 2)]))

    # 3. single-track delete: one of Leon's short sounds under Pei that Leon removed (S4 map)
    al = ep001.load_alignment()
    span = next(m for m in al["muted_track_spans"] if m["track"] == "Leon" and m["raw"][0] > 600
                and m["raw_level_db_above_floor"] > 40 and m["other_track_heard_frac"] > 0.9)
    d0 = snap_cut_media(pool, [ids["Leon"]], S(span["raw"][0]), sr, radius_ms=80)
    d1 = snap_cut_media(pool, [ids["Leon"]], S(span["raw"][1]), sr, radius_ms=80)
    after = LiftRange("Leon", d0, d1).apply(raw)
    r0, r1 = span["raw"]
    emit("03_single_track_delete", raw, after, r0 - CTX, r1 + CTX, r0 - CTX, r1 + CTX,
         dict(leon_raw_s=[round(d0 / sr, 3), round(d1 / sr, 3)], s4_map_raw_s=span["raw"],
              final_s=span["final"]))

    (OUT / "previews.json").write_text(json.dumps(log, indent=1, ensure_ascii=False))
    total = sum(p.stat().st_size for p in outputs)
    print(json.dumps(log, indent=1, ensure_ascii=False))
    print(f"{len(outputs)} files, {total / 1e6:.2f} MB")
    pool.close()


if __name__ == "__main__":
    main()
