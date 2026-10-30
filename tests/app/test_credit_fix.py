"""一键修复曲名和作者 (lacuna_app/credit_fix.py, routes/credit_fix.py): one lookup for an episode's own music
or the library's shared music; results wait for the editor to tick; only ticked ones are written."""
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.credit_fix import CHUNK, request
from lacuna_app.editor import MockEditorAdapter

from .fake_credit_fix import FakeCreditFixAnthropic
from .synth import EPISODE, make_workspace, write_music

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
URL = "/api/library/credit-fix"


@pytest.fixture
def fake():
    return FakeCreditFixAnthropic()


@pytest.fixture
def client(tmp_path, fake):
    ws = make_workspace(tmp_path / "ws")
    return TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent"), credit_fix_client=fake))


def upload(client, path, episode=""):
    params = {"name": Path(path).name, "kind": "interlude"} | ({"episode": episode} if episode else {})
    r = client.post("/api/library/upload", params=params, content=Path(path).read_bytes(),
                    headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200, r.text
    return r.json()["asset"]["id"]


def wait(client, episode=""):
    for _ in range(200):
        v = client.get(URL, params={"episode": episode}).json()
        if v["job"] and v["job"]["state"] != "running":
            return v
        time.sleep(0.05)
    raise AssertionError("credit fix never finished")


def test_episode_fix_only_touches_the_episodes_own_music(client, tmp_path, fake):
    shared = upload(client, write_music(tmp_path / "in" / "片头.wav", 4.0))
    mine = upload(client, write_music(tmp_path / "in" / "bgm_final.wav", 5.0), EPISODE)
    alt = upload(client, write_music(tmp_path / "in" / "alt.wav", 6.0), EPISODE)
    lost = upload(client, write_music(tmp_path / "in" / "乱码.wav", 7.0), EPISODE)

    v = client.get(URL, params={"episode": EPISODE}).json()
    assert v["available"] and v["own"] == 3 and v["unknown"] == 3 and v["job"] is None
    assert shared not in {f["id"] for f in v["files"]}

    r = client.post(URL, json={"episode": EPISODE, "prompt": "全是《午夜凶铃》原声"})
    assert r.status_code == 200, r.text
    v = wait(client, EPISODE)
    job = v["job"]
    assert job["state"] == "done" and job["prompt"] == "全是《午夜凶铃》原声"
    sent = fake.calls[0]
    assert sent["model"] == "claude-opus-5-5" and "全是《午夜凶铃》原声" in sent["messages"][0]["content"]
    assert "片头" not in sent["messages"][0]["content"]          # shared music is the library page's job
    res = {r["asset_id"]: r for r in job["results"]}
    assert res[mine]["pick"] and res[mine]["line"] == "《午夜凶铃》原声 · 川井宪次 — “Theme bgm_final”"
    assert not res[alt]["pick"] and res[alt]["alternatives"] == ["Video Tape — 川井宪次"]
    assert not res[lost]["pick"] and res[lost]["line"] == "" and res[lost]["found"]["title"] is None
    assert job["sources"] == ["https://example.org/ringu-ost"]

    # nothing is written until applied; the editor may correct a field first
    lib = {a["id"]: a for a in client.get("/api/library").json()["assets"]}
    assert lib[mine]["credit"]["status"] == "unknown"
    picks = [{"asset_id": mine, "credit": res[mine]["found"]},
             {"asset_id": alt, "credit": res[alt]["found"] | {"title": "Video Tape"}},
             {"asset_id": lost, "credit": res[lost]["found"]}]          # nothing found: skipped
    out = client.post(f"{URL}/apply", json={"episode": EPISODE, "picks": picks}).json()
    assert out["applied"] == 2 and out["job"] is None and out["unknown"] == 1
    lib = {a["id"]: a for a in client.get("/api/library").json()["assets"]}
    assert lib[mine]["credit"]["status"] == "confirmed" and lib[mine]["credit"]["source"] == "claude"
    assert lib[alt]["credit"]["title"] == "Video Tape" and lib[alt]["credit"]["composer"] == "川井宪次"
    assert lib[lost]["credit"]["status"] == "unknown" and lib[shared]["credit"]["status"] == "unknown"

    # confirmed ones are skipped unless asked to look again
    client.post(URL, json={"episode": EPISODE, "prompt": ""})
    assert [r["asset_id"] for r in wait(client, EPISODE)["job"]["results"]] == [lost]
    client.post(URL, json={"episode": EPISODE, "prompt": "", "redo": True})
    assert len(wait(client, EPISODE)["job"]["results"]) == 3
    assert client.delete(URL, params={"episode": EPISODE}).json()["job"] is None


def test_library_fix_covers_shared_music(client, tmp_path, fake):
    shared = upload(client, write_music(tmp_path / "in" / "opening.wav", 4.0))
    upload(client, write_music(tmp_path / "in" / "mine.wav", 5.0), EPISODE)
    v = client.get(URL).json()
    assert [f["id"] for f in v["files"]] == [shared]
    client.post(URL, json={"prompt": "节目片头"})
    assert [r["asset_id"] for r in wait(client)["job"]["results"]] == [shared]


def test_nothing_to_fix_busy_and_failure(client, tmp_path, fake):
    assert client.post(URL, json={"episode": EPISODE}).status_code == 422       # no music of its own
    assert client.post(URL, json={"episode": "EP_NOPE"}).status_code == 404
    upload(client, write_music(tmp_path / "in" / "a.wav", 4.0), EPISODE)
    fake.delay = 0.5
    assert client.post(URL, json={"episode": EPISODE}).status_code == 200
    assert client.post(URL, json={"episode": EPISODE}).status_code == 409      # one at a time
    assert client.delete(URL, params={"episode": EPISODE}).status_code == 409
    wait(client, EPISODE)
    fake.delay, fake.fail = 0, True
    client.post(URL, json={"episode": EPISODE})
    job = wait(client, EPISODE)["job"]
    assert job["state"] == "failed" and job["results"] == [] and "曲名没有变" in job["message"]


def test_request_is_text_only_and_split_in_chunks():
    files = [{"id": f"a{i}", "name": f"{i}.mp3", "tags": {}, "duration_s": 60.0 + i, "note": "", "kind": "bed"}
             for i in range(CHUNK + 1)]
    req = request(files[:CHUNK], "片尾是主题曲", None)
    body = req["messages"][0]["content"]
    assert "片尾是主题曲" in body and '"duration_s": 60.0' in body and "submit_credits" == req["tools"][1]["name"]
    assert req["tools"][0]["max_uses"] == 15
    profile = {"legacy": False, "show_name": "周末电影院"}
    assert "《周末电影院》" in request(files[:1], "", profile)["system"]
    assert "Leon" not in request(files[:1], "", profile)["system"]
