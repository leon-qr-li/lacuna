"""Build a per-track LACUNA EDL from the S4 alignment map of EP001 (Leon's real edit)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from lacuna_core import LiftRange, MediaRef, Project, SetTrackGain, new_timeline
from lacuna_core.edl import Clip, Track, replace

ALIGNMENT = Path(__file__).resolve().parents[1] / "s4_alignment/out/ep001_alignment.json"
RAW_DIR = Path("/mnt/user-data/uploads/Projects")
RAW = {"Leon": RAW_DIR / "原始双轨_Leon.wav", "Pei": RAW_DIR / "原始双轨_Pei.wav"}
FINAL = RAW_DIR / "最终成品.mp3"
SRC_KEY = {"Leon": "leon_src", "Pei": "pei_src"}


def load_alignment(path: Path = ALIGNMENT) -> dict:
    return json.loads(path.read_text())


def build_project(al: dict, media: dict[str, MediaRef], f0: float = 0.0, f1: float | None = None,
                  apply_mutes: bool = True) -> tuple[Project, dict]:
    """Timeline t=0 corresponds to final time f0. Returns (project, info).

    Base timeline: for each raw segment of the map, one clip per track playing that track's
    source span (consecutive segments that continue the same source join seamlessly).
    Logged ops on top: per-track gain (median map gain, Leon about +7 dB) and LiftRange for
    every span where the map says a track is muted in the final (Leon's single-track deletes).
    """
    by_track = {name: next(m for m in media.values() if Path(m.path) == RAW[name]) for name in RAW}
    sr = next(iter(media.values())).sample_rate
    f1 = al["stats"]["final_duration_s"] if f1 is None else f1
    T = lambda f: int(round((f - f0) * sr))
    tracks = []
    for name, ref in by_track.items():
        clips = []
        for s in al["segments"]:
            if s["type"] != "raw" or s["final_end"] <= f0 or s["final_start"] >= f1:
                continue
            fs, fe = max(s["final_start"], f0), min(s["final_end"], f1)
            src0 = s[SRC_KEY[name]][0] + (fs - s["final_start"])
            t0, t1 = T(fs), T(fe)
            src_in = int(round(src0 * sr))
            if src_in < 0:                       # map can start a hair before raw t=0
                t0, src_in = t0 - src_in, 0
            src_out = min(src_in + (t1 - t0), ref.frames)
            if src_out - src_in > 0:
                clips.append(Clip(f"{name[0]}{len(clips)}", ref.media_id, src_in, src_out, t0))
        tracks.append(Track(name, tuple(clips)))
    base = replace(new_timeline(sr, RAW), tracks=tuple(tracks))
    p = Project(media, base)
    gains = al["stats"]["median_gain"]
    for name in RAW:
        p.apply(SetTrackGain(name, round(20 * np.log10(gains[name]), 2)))
    n_mutes = 0
    if apply_mutes:
        for m in al["muted_track_spans"]:
            a, b = max(m["final"][0], f0), min(m["final"][1], f1)
            if b - a > 0.005:
                p.apply(LiftRange(m["track"], T(a), T(b)))
                n_mutes += 1
    events = [e for e in al["edit_events"] if f0 <= e["final_pos"] < f1]
    inserts = [(max(i["final_start"], f0) - f0, min(i["final_end"], f1) - f0)
               for i in al["inserts"] if i["final_end"] > f0 and i["final_start"] < f1]
    info = dict(f0=f0, f1=f1, clips={t.name: len(t.clips) for t in base.tracks}, lifts=n_mutes,
                events=len(events), single_track_events=sum(e["kind"] != "joint" for e in events),
                inserts_s=inserts)
    return p, info
