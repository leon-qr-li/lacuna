import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from lacuna_app import Episode, Workspace, create_app
from lacuna_app.audio import parse_range
from lacuna_app.editor import ChatContext, ClaudeEditorAdapter, MockEditorAdapter, make_adapter
from lacuna_app.episode import subtract, to_base, to_tl
from lacuna_app.store import PathError, atomic_write_json, check_id, read_json

from .synth import EPISODE, SR, make_workspace

EP = f"/api/episodes/{EPISODE}"


@pytest.fixture
def ws(tmp_path):
    return make_workspace(tmp_path / "ws")


@pytest.fixture
def client(ws):
    return TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))


def summary(client):
    r = client.get(EP)
    assert r.status_code == 200
    return r.json()


def wav_of(content: bytes):
    x, sr = sf.read(io.BytesIO(content), dtype="float32")
    return x, sr


# ---------------------------------------------------------------- listing / loading

def test_list_and_load(client):
    eps = client.get("/api/episodes").json()["episodes"]
    assert [e["id"] for e in eps] == [EPISODE]
    s = summary(client)
    assert s["raw_duration"] == 60.0
    # first cut removes 1.1 + 4.4 + 1.4 + 0.6 s on all tracks
    assert s["duration"] == pytest.approx(60 - 7.5, abs=1e-3)
    assert [t["name"] for t in s["tracks"]] == ["Leon", "Pei"]
    assert s["pending_review"] == 1
    e3 = next(e for e in s["edits"] if e["id"] == "e003")
    assert e3["consequential"] and e3["category"] == "content" and e3["reason"]
    assert e3["t"] == pytest.approx(26.3 - 1.1, abs=1e-3) and e3["len"] == pytest.approx(4.4)
    assert {r["category"] for r in s["routine"]} >= {"pause", "crosstalk", "filler", "loudness"}
    assert not s["can_undo"] and not s["can_redo"]


def test_unknown_and_traversal_ids(client):
    assert client.get("/api/episodes/nope").status_code == 404
    for bad in ["..", "..%2F..%2Fetc", ".hidden", "a%5Cb", "a:b"]:
        assert client.get(f"/api/episodes/{bad}").status_code in (400, 404)
    with pytest.raises(PathError):
        check_id("../x")
    with pytest.raises(PathError):
        Workspace("/tmp").episode_dir("..")


# ---------------------------------------------------------------- audio

def test_audio_range_matches_renderer(client, ws):
    s = summary(client)
    url = s["audio_url"]
    full = client.get(url)
    assert full.status_code == 200 and full.headers["accept-ranges"] == "bytes"
    n = int(round(s["duration"] * SR))
    assert len(full.content) == 44 + 2 * n == int(full.headers["content-length"])
    x, sr = wav_of(full.content)
    assert sr == SR and len(x) == n

    r = client.get(url, headers={"Range": "bytes=1000-50999"})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 1000-50999/{len(full.content)}"
    assert r.content == full.content[1000:51000]
    # odd offsets and open-ended ranges
    r = client.get(url, headers={"Range": "bytes=12345-"})
    assert r.content == full.content[12345:]
    assert client.get(url, headers={"Range": "bytes=99999999-"}).status_code == 416

    # rendered audio equals lacuna_core's renderer for the same timeline
    ep = Episode(Workspace(ws), EPISODE)
    ref = ep.render(ep.enabled, 0, n)[:, 0]
    assert np.max(np.abs(np.clip(ref, -1, 1) - x)) < 2 / 32767
    ep.close()


def test_old_version_url_still_serves_its_own_audio(client):
    s0 = summary(client)
    s1 = client.post(f"{EP}/edits/e003/review", json={"action": "restore"}).json()
    assert s1["audio_url"] != s0["audio_url"]
    old = client.get(s0["audio_url"])
    new = client.get(s1["audio_url"])
    assert len(new.content) - len(old.content) == 2 * int(round(4.4 * SR))
    assert client.get(f"{EP}/audio/deadbeefdeadbeef.wav").status_code == 404


def test_parse_range():
    assert parse_range("bytes=0-9", 100) == (0, 9)
    assert parse_range("bytes=90-", 100) == (90, 99)
    assert parse_range("bytes=-10", 100) == (90, 99)
    assert parse_range("bytes=0-1000", 100) == (0, 99)
    assert parse_range("bytes=100-", 100) is None
    assert parse_range("bytes=0-1,5-6", 100) is None
    assert parse_range(None, 100) is None


# ---------------------------------------------------------------- A/B

def test_edit_ab(client):
    ab = client.get(f"{EP}/edits/e003/ab").json()
    b, a = ab["before"], ab["after"]
    assert b["edit_len"] == pytest.approx(4.4, abs=1e-3) and a["edit_len"] == 0
    assert b["edit_at"] == pytest.approx(10.0, abs=1e-3)
    assert b["duration"] - a["duration"] == pytest.approx(4.4, abs=1e-3)
    xb, sr = wav_of(client.get(b["url"]).content)
    xa, _ = wav_of(client.get(a["url"]).content)
    assert sr == SR and len(xb) - len(xa) == int(round(4.4 * SR))
    # identical before the edit point (same source, same mix)
    k = int(9.0 * SR)
    assert np.max(np.abs(xb[:k] - xa[:k])) < 1e-3
    assert client.get(f"{EP}/edits/zzz/ab").status_code == 404
    assert client.get(f"{EP}/clips/nothere.wav").status_code == 404


def test_edit_text(client):
    lines = client.get(f"{EP}/edits/e003/text").json()["lines"]
    removed = [w for ln in lines for w in ln["words"] if w["removed"]]
    kept = [w for ln in lines for w in ln["words"] if not w["removed"]]
    assert removed and kept
    assert all(ln["speaker"] == "Leon" for ln in lines if any(w["removed"] for w in ln["words"]))


# ---------------------------------------------------------------- review / undo / redo / ops

def test_review_restore_undo_redo(client):
    s = client.post(f"{EP}/edits/e003/review", json={"action": "restore", "playhead": 30.0}).json()
    assert s["duration"] == pytest.approx(52.5 + 4.4, abs=1e-3)
    e3 = next(e for e in s["edits"] if e["id"] == "e003")
    assert e3["status"] == "restored" and e3["approved"]
    assert s["playhead"] == pytest.approx(34.4, abs=1e-3)       # same moment of speech
    assert s["can_undo"] and s["undo_label"].startswith("恢复")

    s = client.post(f"{EP}/undo", json={"playhead": 34.4}).json()
    assert s["duration"] == pytest.approx(52.5, abs=1e-3) and s["can_redo"]
    assert s["playhead"] == pytest.approx(30.0, abs=1e-3)
    e3 = next(e for e in s["edits"] if e["id"] == "e003")
    assert e3["status"] == "applied" and not e3["approved"]

    s = client.post(f"{EP}/redo", json={}).json()
    assert s["duration"] == pytest.approx(56.9, abs=1e-3)
    assert client.post(f"{EP}/redo", json={}).status_code == 409

    s = client.post(f"{EP}/edits/e003/review", json={"action": "apply"}).json()
    assert s["duration"] == pytest.approx(52.5, abs=1e-3)
    s = client.post(f"{EP}/edits/e001/review", json={"action": "keep"}).json()
    assert next(e for e in s["edits"] if e["id"] == "e001")["approved"]
    assert client.post(f"{EP}/edits/e001/review", json={"action": "bogus"}).status_code == 422


def test_undo_with_empty_history(client):
    assert client.post(f"{EP}/undo", json={}).status_code == 409


def test_apply_op_and_overlap_conflict(client):
    op = {"op": "cut", "start": int(16.2 * SR), "end": int(17.6 * SR), "tracks": None}
    s = client.post(f"{EP}/ops", json={"op": op, "title": "手动收紧"}).json()
    assert s["duration"] == pytest.approx(52.5 - 1.4, abs=1e-3)
    assert any(e["id"] == s["edit_id"] and e["source"] == "manual" for e in s["edits"])
    # overlapping an applied cut is refused, state unchanged
    bad = {"op": "cut", "start": int(4.0 * SR), "end": int(5.0 * SR), "tracks": None}
    r = client.post(f"{EP}/ops", json={"op": bad})
    assert r.status_code == 409
    assert summary(client)["duration"] == pytest.approx(51.1, abs=1e-3)
    assert client.post(f"{EP}/ops", json={"op": {"op": "nope"}}).status_code == 422
    s = client.post(f"{EP}/undo", json={}).json()
    assert s["duration"] == pytest.approx(52.5, abs=1e-3)


# ---------------------------------------------------------------- chat

def test_chat_pause_proposal_preview_approve(client):
    r = client.post(f"{EP}/chat", json={"text": "这里停顿短一点", "playhead": 15.5}).json()
    p = r["proposal"]
    assert r["adapter"] == "mock" and p and "停顿" in r["reply"]
    # nothing changes until approval
    s = summary(client)
    assert s["duration"] == pytest.approx(52.5, abs=1e-3)
    assert [x["id"] for x in s["proposals"]] == [p["id"]]
    ab = client.get(f"{EP}/proposals/{p['id']}/ab").json()
    assert ab["before"]["duration"] - ab["after"]["duration"] == pytest.approx(1.6, abs=0.1)
    s = client.post(f"{EP}/proposals/{p['id']}/approve", json={"playhead": 15.5}).json()
    assert s["duration"] == pytest.approx(52.5 - 1.6, abs=0.1)
    chat_edit = next(e for e in s["edits"] if e["source"] == "chat")
    assert chat_edit["category"] == "pause" and chat_edit["status"] == "applied"
    assert s["proposals"] == []
    assert client.post(f"{EP}/proposals/{p['id']}/approve", json={}).status_code == 409
    s = client.post(f"{EP}/undo", json={}).json()
    assert s["duration"] == pytest.approx(52.5, abs=1e-3)
    assert not any(e["source"] == "chat" for e in s["edits"])


def test_chat_restore_and_delete_sentence(client):
    r = client.post(f"{EP}/chat", json={"text": "把前面那句恢复一下", "playhead": 26.0}).json()
    assert r["proposal"]["target"] == "e003"
    s = client.post(f"{EP}/proposals/{r['proposal']['id']}/approve", json={}).json()
    assert s["duration"] == pytest.approx(56.9, abs=1e-3)

    r = client.post(f"{EP}/chat", json={"text": "删掉这句", "playhead": 18.0}).json()
    p = r["proposal"]
    assert p and "删掉" in r["reply"]
    s = client.post(f"{EP}/proposals/{p['id']}/approve", json={}).json()
    # Leon's 18.0-22.0 turn (4 s) and part of the following pause are gone
    assert 56.9 - s["duration"] == pytest.approx(4.0, abs=0.3)


def test_chat_discard_and_superseded(client):
    p1 = client.post(f"{EP}/chat", json={"text": "停顿短一点", "playhead": 15.5}).json()["proposal"]
    p2 = client.post(f"{EP}/chat", json={"text": "停顿短一点", "playhead": 15.5}).json()["proposal"]
    s = summary(client)
    assert [x["id"] for x in s["proposals"]] == [p2["id"]]
    assert client.post(f"{EP}/proposals/{p1['id']}/approve", json={}).status_code in (404, 409)
    s = client.post(f"{EP}/proposals/{p2['id']}/discard", json={}).json()
    assert s["proposals"] == [] and s["duration"] == pytest.approx(52.5, abs=1e-3)


def test_chat_unknown_command(client):
    r = client.post(f"{EP}/chat", json={"text": "这段加点音乐", "playhead": 10}).json()
    assert r["proposal"] is None and "规则引擎" in r["reply"]
    assert client.post(f"{EP}/chat", json={"text": "", "playhead": 1}).status_code == 422


# ---------------------------------------------------------------- persistence & safety

def test_state_persists_across_restart(ws):
    c1 = TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))
    c1.post(f"{EP}/edits/e003/review", json={"action": "restore"})
    c2 = TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))
    s = c2.get(EP).json()
    assert s["duration"] == pytest.approx(56.9, abs=1e-3) and s["can_undo"]
    # state.json holds a valid lacuna_core Project whose log is the render recipe
    st = read_json(Path(ws) / "episodes" / EPISODE / "state.json")
    from lacuna_core import Project
    proj = Project.from_json(json.dumps(st["project"]))
    assert proj.timeline.length == int(round(56.9 * SR))


def test_raw_media_never_written(ws, client):
    raw = sorted((Path(ws) / "episodes" / EPISODE / "raw").glob("*.wav"))
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in raw}
    client.post(f"{EP}/edits/e003/review", json={"action": "restore"})
    client.post(f"{EP}/chat", json={"text": "停顿短一点", "playhead": 15.5})
    client.get(summary(client)["audio_url"])
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in raw} == before
    with pytest.raises(PathError):
        atomic_write_json(raw[0], {"x": 1}, protected=(raw[0],))


def test_atomic_write_survives_crash(tmp_path, monkeypatch):
    p = tmp_path / "state.json"
    atomic_write_json(p, {"v": 1})

    class Boom(Exception):
        pass

    def explode(*a, **k):
        raise Boom()

    import lacuna_app.store as store
    monkeypatch.setattr(store.json, "dumps", explode)
    with pytest.raises(Boom):
        atomic_write_json(p, {"v": 2})
    assert read_json(p) == {"v": 1}
    assert not list(tmp_path.glob("*.tmp"))
    monkeypatch.undo()
    # torn main file -> fall back to the .bak copy
    atomic_write_json(p, {"v": 3})
    p.write_text("{truncated")
    assert read_json(p) == {"v": 1}


# ---------------------------------------------------------------- mapping & adapters

def test_timeline_base_mapping():
    cuts = [(10, 20), (30, 35)]
    assert to_tl(5, cuts) == 5 and to_tl(15, cuts) == 10 and to_tl(25, cuts) == 15 and to_tl(40, cuts) == 25
    assert to_base(10, cuts) == 20 and to_base(10, cuts, right=False) == 10
    assert to_base(15, cuts) == 25 and to_base(25, cuts) == 40
    for x in (0, 9, 20, 29, 35, 50):
        assert to_base(to_tl(x, cuts), cuts) == x
    assert subtract(0, 40, cuts) == [(0, 10), (20, 30), (35, 40)]


def test_adapter_selection_and_claude_stub(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert make_adapter("auto").name == "mock"
    claude = ClaudeEditorAdapter()
    assert not claude.available
    ctx = ChatContext("停顿短一点", 12.0, 60.0, [], None)
    assert "AI 密钥" in claude.propose(ctx).message              # no network call
    req = ClaudeEditorAdapter(api_key="test").build_request(ctx)
    assert req["model"] == "claude-opus-5-5" and req["tools"][0]["name"] == "propose_edit"
    assert "停顿短一点" in req["messages"][0]["content"]
