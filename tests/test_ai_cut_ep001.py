"""AI first cut (S5 v2 held-out ops) on the real EP001 recording, through the app.

Skipped when the raw tracks are not on this machine. Raw dir: $LACUNA_EP001_DIR/raw (workspace
layout, Leon.wav / Pei.wav) or /mnt/user-data/uploads/Projects (原始双轨_*.wav).
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import make_ai_episode  # noqa: E402

RAW_DIR = (Path(os.environ["LACUNA_EP001_DIR"]) / "raw" if os.environ.get("LACUNA_EP001_DIR")
           else make_ai_episode.RAW_DIR)
OPS = ROOT / "spikes/s5_first_cut/out/ai_v2_heldout_ops.json"


def _raw():
    try:
        return make_ai_episode.find_raw(RAW_DIR)
    except FileNotFoundError:
        return None


pytestmark = pytest.mark.skipif(_raw() is None or not OPS.is_file(), reason="EP001 raw audio not available")


@pytest.fixture(scope="module")
def ep001_ai(tmp_path_factory):
    from lacuna_app.ai_cut import load_tokens
    from lacuna_app.episode import create_episode
    from lacuna_app.store import Workspace
    from lacuna_core import MediaRef
    # path-based ids are enough for a test (the script hashes the files)
    media = {n: MediaRef.probe(p, media_id=f"raw:{n}") for n, p in _raw().items()}
    ops = json.loads(OPS.read_text(encoding="utf-8"))
    project, edits, transcript, report = make_ai_episode.build(media, ops, load_tokens(make_ai_episode.TOKENS), 0.0, None)
    ws = tmp_path_factory.mktemp("ws")
    create_episode(Workspace(ws), "EP001_AI", {"title": "EP001 · AI 第一刀", "demo": False, "raw_offset_s": 0.0},
                   project, edits, transcript)
    return ws, report, len(ops["ops"])


def test_v2_ops_convert_completely(ep001_ai):
    _, report, n_ops = ep001_ai
    assert report.ops_in == n_ops
    # the only skips are the pause positions the S5 scorer also rejects (17 for v2)
    assert sum(report.skipped.values()) <= 20
    assert set(report.skipped) <= {"停顿位置落在词内（与评分脚本一致，跳过）", "与其他删除重叠"}
    assert report.edits_out >= n_ops - 20


def test_v2_episode_through_the_api(ep001_ai):
    from fastapi.testclient import TestClient
    from lacuna_app.editor import MockEditorAdapter
    from lacuna_app.server import create_app
    ws, _, _ = ep001_ai
    c = TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))
    t0 = time.perf_counter()
    s = c.get("/api/episodes/EP001_AI").json()
    open_s = time.perf_counter() - t0
    assert s["demo"] is False and s["raw_duration"] == pytest.approx(4411.9, abs=0.5)
    removed = s["raw_duration"] - s["duration"]
    assert 300 < removed < 480           # S5 v2 scored ~380 s removed on the held-out half
    by_id = {e["id"]: e for e in s["edits"]}
    review = [by_id[i] for i in s["review"]]
    assert review[0]["category"] == "content"
    n_content = sum(e["category"] == "content" for e in review)
    assert all(e["category"] == "content" for e in review[:n_content])
    assert all(review[i]["len"] >= review[i + 1]["len"] for i in range(n_content, len(review) - 1))
    assert all(e["raw"][0] >= 2195 for e in s["edits"])      # held-out half only
    assert open_s < 3.0                                     # generous: CI machines vary
    # restore / undo stay fast on the full 73 min timeline
    t0 = time.perf_counter()
    r = c.post(f"/api/episodes/EP001_AI/edits/{review[0]['id']}/review", json={"action": "restore", "playhead": 2500})
    assert r.status_code == 200 and time.perf_counter() - t0 < 2.0
    assert r.json()["duration"] == pytest.approx(s["duration"] + review[0]["len"], abs=1e-3)
    c.post("/api/episodes/EP001_AI/undo", json={})
    ab = c.get(f"/api/episodes/EP001_AI/edits/{review[0]['id']}/ab").json()
    wav = c.get(ab["after"]["url"]).content
    x = np.frombuffer(wav[44:], "<i2")
    assert len(x) > 10 * 44100 and np.abs(x).max() > 1000
    lines = c.get(f"/api/episodes/EP001_AI/edits/{review[0]['id']}/text").json()["lines"]
    assert any(w["removed"] for ln in lines for w in ln["words"])
