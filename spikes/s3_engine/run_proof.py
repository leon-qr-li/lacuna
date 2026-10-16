#!/usr/bin/env python3
"""S3 proof on EP001: rebuild Leon's real per-track edit as a LACUNA EDL, render it, compare
with the published final, and measure render speed, peak RAM, preview latency and seams.

  python3 spikes/s3_engine/run_proof.py --scratch /some/dir        # everything (~3-4 min)

Writes numbers only to spikes/s3_engine/out/ (results.json, ep001_window_project.json).
Full renders go to --scratch (outside the repo; they contain audio).
"""
from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, sosfilt_zi

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lacuna_core import (CutRange, MediaRef, Previewer, RenderSettings, RenderStats, Renderer,
                         SegmentCache,
                         SourcePool, check_seams, seams)
import ep001

OUT = Path(__file__).resolve().parent / "out"
WINDOW = (150.0, 390.0)        # 4 min of final; 45 edit events, 23 single-track, 22 mutes


def media_table(cache: Path) -> dict[str, MediaRef]:
    """Hash the raw tracks once (read-only) and remember the ids."""
    if cache.exists():
        refs = [MediaRef.from_dict(d) for d in json.loads(cache.read_text())]
    else:
        refs = [MediaRef.probe(p) for p in ep001.RAW.values()]
        cache.write_text(json.dumps([r.to_dict() for r in refs], indent=1))
    return {r.media_id: r for r in refs}


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


class FinalReader:
    """Streams the final MP3 as mono float32 at the timeline rate via ffmpeg."""

    def __init__(self, f0: float, sr: int, dur: float | None = None):
        cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(ep001.FINAL), "-ss", f"{f0:.6f}"]
        if dur:
            cmd += ["-t", f"{dur:.6f}"]
        cmd += ["-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE)

    def read(self, n: int) -> np.ndarray:
        b = self.p.stdout.read(4 * n)
        return np.frombuffer(b, dtype=np.float32)

    def close(self):
        self.p.stdout.close()
        self.p.wait()


class Corr:
    """Streaming comparison of render vs final: global NCC and 1 s window NCCs, full band and
    speech band (100-3800 Hz, comparable to S4's 8 kHz analysis)."""

    def __init__(self, sr: int, exclude_s: list[tuple[float, float]]):
        self.sr, self.exclude = sr, exclude_s
        self.sos = butter(4, [100, 3800], btype="band", fs=sr, output="sos")
        self.zi = [sosfilt_zi(self.sos) * 0, sosfilt_zi(self.sos) * 0]
        self.acc = {k: np.zeros(3) for k in ("full", "band")}
        self.win = {k: [] for k in ("full", "band")}
        self.buf = {k: (np.zeros(0), np.zeros(0)) for k in ("full", "band")}
        self.done = {k: 0 for k in ("full", "band")}   # 1 s windows consumed

    def add(self, y: np.ndarray, x: np.ndarray):
        n = min(len(y), len(x))
        y, x = y[:n].astype(np.float64), x[:n].astype(np.float64)
        yb, self.zi[0] = sosfilt(self.sos, y, zi=self.zi[0])
        xb, self.zi[1] = sosfilt(self.sos, x, zi=self.zi[1])
        for k, (a, b) in (("full", (y, x)), ("band", (yb, xb))):
            ba, bb = self.buf[k]
            ba, bb = np.concatenate([ba, a]), np.concatenate([bb, b])
            w = self.sr
            nw = len(ba) // w
            for i in range(nw):
                sa, sb = ba[i * w:(i + 1) * w], bb[i * w:(i + 1) * w]
                t = self.done[k] + i
                if any(e0 - 1 <= t <= e1 + 1 for e0, e1 in self.exclude):
                    continue
                self.acc[k] += [np.dot(sa, sb), np.dot(sa, sa), np.dot(sb, sb)]
                if np.dot(sb, sb) > 1e-4 * w * 1e-3:        # skip near-silent windows
                    self.win[k].append(np.dot(sa, sb) / np.sqrt(np.dot(sa, sa) * np.dot(sb, sb) + 1e-20))
            self.buf[k] = (ba[nw * w:], bb[nw * w:])
            self.done[k] += nw

    def result(self) -> dict:
        out = {}
        for k in ("full", "band"):
            xy, xx, yy = self.acc[k]
            w = np.array(self.win[k])
            out[k] = dict(global_ncc=round(float(xy / np.sqrt(xx * yy)), 4), windows=len(w),
                          window_ncc_pct={p: round(float(np.percentile(w, p)), 3) for p in (5, 10, 25, 50, 75, 90)},
                          windows_below_0_8=int((w < 0.8).sum()))
        return out


def render_and_compare(project, f0: float, inserts, settings: RenderSettings, wav: Path | None) -> dict:
    tl = project.timeline
    sr = tl.sample_rate
    pool = SourcePool(project.media)
    r = Renderer(pool, settings)
    final = FinalReader(f0, sr, tl.length / sr)
    corr = Corr(sr, [(int(a), int(b) + 1) for a, b in inserts])
    t0 = time.perf_counter()
    writer = None
    if wav is not None:
        writer = sf.SoundFile(str(wav), "w", sr, settings.channels, subtype="PCM_16")
    stats = RenderStats()
    for chunk in r.iter_chunks(tl, stats=stats):
        if writer is not None:
            writer.write(chunk)
        corr.add(chunk[:, 0], final.read(len(chunk)))
    wall = time.perf_counter() - t0
    if writer is not None:
        writer.close()
    final.close()
    pool.close()
    return dict(duration_s=round(tl.length / sr, 2), wall_s_incl_compare=round(wall, 2),
                peak=round(stats.peak, 3), limited_samples=stats.limited,
                correlation=corr.result())


def lag_check(project, f0: float, settings) -> dict:
    """Cross-correlate 60 s of render vs final to confirm sample alignment (+-50 ms)."""
    tl = project.timeline
    sr = tl.sample_rate
    with SourcePool(project.media) as pool:
        y = Renderer(pool, settings).render(tl, 0, 60 * sr)[:, 0].astype(np.float64)
    f = FinalReader(f0, sr, 60)
    x = f.read(60 * sr).astype(np.float64)
    f.close()
    m = int(0.05 * sr)
    core = y[m:-m]
    c = [np.dot(core, x[m + k:m + k + len(core)]) for k in range(-m, m + 1)]
    best = int(np.argmax(c)) - m
    return dict(best_lag_samples=best, best_lag_ms=round(1000 * best / sr, 2))


def render_only(project, settings, path: Path) -> dict:
    with SourcePool(project.media) as pool:
        r = Renderer(pool, settings)
        t0 = time.perf_counter()
        stats = r.render_to_file(project.timeline, path, subtype="PCM_16")
        wall = time.perf_counter() - t0
    dur = project.timeline.length / project.timeline.sample_rate
    return dict(audio_s=round(dur, 1), wall_s=round(wall, 2), x_realtime=round(dur / wall, 1),
                peak_rss_mb=round(peak_rss_mb(), 1), limited_samples=stats.limited)


def seam_metrics(project, settings_list) -> dict:
    tl = project.timeline
    sr = tl.sample_rate
    out = {}
    with SourcePool(project.media) as pool:
        for st in settings_list:
            r = Renderer(pool, st)
            per_track = {}
            for i, tr in enumerate(tl.tracks):
                y = r.render_track(tl, i, 0, tl.length)
                sl = [s for s in seams(tl) if s.track == tr.name]
                rep = check_seams(y, sr, sl)
                dr = np.array([x.delta_ratio for x in rep])
                hr = np.array([x.hf_ratio for x in rep])
                per_track[tr.name] = dict(
                    seams=len(rep), clicks=sum(x.click for x in rep),
                    delta_ratio_median=round(float(np.median(dr)), 2), delta_ratio_p95=round(float(np.percentile(dr, 95)), 2),
                    hf_ratio_median=round(float(np.median(hr)), 2), hf_ratio_p95=round(float(np.percentile(hr, 95)), 2),
                    worst=[x.to_dict() for x in sorted(rep, key=lambda x: -x.delta_ratio)[:3]])
            out[f"xfade_{st.xfade_ms:g}ms"] = per_track
    return out


def preview_latency(project, settings, al) -> dict:
    """+-10 s previews on the full-episode timeline at 44.1 kHz: cold / warm / after a local
    edit / after an upstream edit, at 8 edit points of the real map."""
    tl = project.timeline
    sr = tl.sample_rate
    events = [e["final_pos"] for e in al["edit_events"]][::60][:8]
    res = {"cold": [], "warm": [], "local_edit": [], "upstream_edit": [], "ab_pair": []}
    with SourcePool(project.media) as pool:
        r = Renderer(pool, settings)
        for f in events:
            pv = Previewer(r, SegmentCache())
            t = int(f * sr)
            r._plans.clear()
            res["cold"].append(pv.around(tl, t).seconds)
            res["warm"].append(pv.around(tl, t).seconds)
            local = CutRange(t + sr, t + sr + int(0.3 * sr)).apply(tl)
            lr = pv.around(local, t)
            res["local_edit"].append(lr.seconds)
            up = CutRange(max(t - 60 * sr, 0), max(t - 60 * sr, 0) + int(0.5 * sr)).apply(tl)
            res["upstream_edit"].append(pv.around(up, t - int(0.5 * sr)).seconds)
            a, b = Previewer(r, SegmentCache()).ab(tl, local, t + sr, t + sr)
            res["ab_pair"].append(a.seconds + b.seconds)
    return {k: dict(median_s=round(float(np.median(v)), 3), max_s=round(float(np.max(v)), 3))
            for k, v in res.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", type=Path, required=True)
    ap.add_argument("--only", choices=["render-full"], default=None)
    args = ap.parse_args()
    args.scratch.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(exist_ok=True)
    media = media_table(OUT / "media_ids.json")
    al = ep001.load_alignment()
    settings = RenderSettings(xfade_ms=16, channels=1, chunk_s=5.0)

    if args.only == "render-full":           # separate process -> clean peak RSS
        t0 = time.perf_counter()
        p, info = ep001.build_project(al, media)
        build_s = time.perf_counter() - t0
        res = render_only(p, settings, args.scratch / "ep001_full_render.wav")
        res.update(build_edl_s=round(build_s, 2), ops=len(p.ops), clips=info["clips"])
        print(json.dumps(res))
        return

    results: dict = {}
    # 1. window proof
    p, info = ep001.build_project(al, media, *WINDOW)
    (OUT / "ep001_window_project.json").write_text(p.to_json())
    results["window"] = dict(info=info, seconds=WINDOW)
    results["window"]["lag"] = lag_check(p, WINDOW[0], settings)
    results["window"]["compare"] = render_and_compare(p, WINDOW[0], info["inserts_s"], settings,
                                                      args.scratch / "ep001_window_render.wav")
    p_nomute, _ = ep001.build_project(al, media, *WINDOW, apply_mutes=False)
    results["window"]["compare_without_single_track_lifts"] = render_and_compare(
        p_nomute, WINDOW[0], info["inserts_s"], settings, None)["correlation"]
    results["window"]["seams"] = seam_metrics(p, [settings, RenderSettings(xfade_ms=0)])
    print(json.dumps(results["window"], indent=1)[:3000], flush=True)

    # 2. full-episode render speed + RAM (subprocess)
    out = subprocess.run([sys.executable, __file__, "--scratch", str(args.scratch), "--only", "render-full"],
                         capture_output=True, text=True, check=True)
    results["full_render"] = json.loads(out.stdout.strip().splitlines()[-1])
    print(results["full_render"], flush=True)

    # 3. full-episode correlation vs final
    pf, finfo = ep001.build_project(al, media)
    results["full_compare"] = render_and_compare(pf, 0.0, finfo["inserts_s"], settings, None)
    results["full_compare"]["info"] = finfo
    print(results["full_compare"], flush=True)

    # 4. preview latency on the full timeline
    results["preview_latency"] = preview_latency(pf, settings, al)
    print(results["preview_latency"], flush=True)
    results["edl_json_bytes_full"] = len(pf.to_json().encode())
    (OUT / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
