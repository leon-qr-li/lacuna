"""Integration on real EP001 audio; skipped when the raw tracks are not on this machine."""
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "spikes/s3_engine"))
import ep001  # noqa: E402

pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in [*ep001.RAW.values(), ep001.FINAL]) or shutil.which("ffmpeg") is None,
    reason="EP001 raw/final audio or ffmpeg not available")


def test_ep001_window_rebuild_matches_final():
    from lacuna_core import MediaRef, RenderSettings, Renderer, SourcePool, check_seams, seams
    from scipy.signal import butter, sosfiltfilt
    # quick ids (path-based) are enough here; the proof script uses full content hashes
    media = {f"raw:{n}": MediaRef.probe(p, media_id=f"raw:{n}") for n, p in ep001.RAW.items()}
    f0, f1 = 200.0, 230.0
    p, info = ep001.build_project(ep001.load_alignment(), media, f0, f1)
    assert info["single_track_events"] > 0
    sr = p.timeline.sample_rate
    with SourcePool(media) as pool:
        r = Renderer(pool, RenderSettings())
        y = r.render(p.timeline, 0, p.timeline.length)[:, 0].astype(np.float64)
        for i, tr in enumerate(p.timeline.tracks):
            solo = r.render_track(p.timeline, i, 0, p.timeline.length)
            rep = check_seams(solo, sr, [s for s in seams(p.timeline) if s.track == tr.name])
            assert rep and not any(x.click for x in rep)
    raw = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(ep001.FINAL),
                          "-ss", str(f0), "-t", str(f1 - f0), "-ac", "1", "-ar", str(sr),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).astype(np.float64)[:len(y)]
    sos = butter(4, [100, 3800], btype="band", fs=sr, output="sos")
    yb, xb = sosfiltfilt(sos, y[:len(x)]), sosfiltfilt(sos, x)
    ncc = np.dot(yb, xb) / np.sqrt(np.dot(yb, yb) * np.dot(xb, xb))
    assert ncc > 0.9
