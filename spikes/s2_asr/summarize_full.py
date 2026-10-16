"""Summarize full-track (73.5 min) runs: throughput, RAM, SenseVoice event tags.

Usage: python summarize_full.py FULL_RUN_DIR > out/fulltrack_summary.json
(FULL_RUN_DIR holds run_paraformer.py / run_sensevoice.py outputs for the *_full.wav files.)
"""
import glob
import json
import os
import sys
from collections import Counter

from compare import count_fillers, norm

res = {}
for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.json"))):
    d = json.load(open(p, encoding="utf-8"))
    t = norm(d["text"])
    r = {"audio_s": d["audio_s"], "wall_s": d["wall_s"], "rtf": d["rtf"], "peak_rss_mb": d["peak_rss_mb"],
         "chars": len(t), "vad_segments": len(d["segments"]), "fillers": count_fillers(t)}
    if d["engine"].startswith("sensevoice"):
        r["event_tags"] = dict(Counter(s["event"] for s in d["segments"]))
        r["emotion_tags"] = dict(Counter(s.get("emotion") for s in d["segments"]))
        r["non_speech_event_segments"] = [
            {"start": s["start"], "end": s["end"], "event": s["event"], "text": s["text"]}
            for s in d["segments"] if s["event"] not in ("Speech", None)]
    res[os.path.basename(p)[:-5]] = r
json.dump(res, sys.stdout, ensure_ascii=False, indent=1)
