"""Phase 11 上传喜马拉雅: the checklist finds the newest WAV, publish pack and cover, and says what is
missing or out of date; the cover downloads with the episode's name."""
import json
import os
import time
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.poster import ClaudeDesigner, Posters
from lacuna_app.publish import ClaudePublisher, Publisher
from lacuna_app.store import Workspace
from lacuna_app.upload import UPLOAD_PAGE, cover_path, latest_wav, save_cover

from .fake_claude import FakePosterAnthropic, FakePublishAnthropic
from .synth import EPISODE, make_workspace

EP = f"/api/episodes/{EPISODE}"


def wait(client, path, timeout=60):
    t = time.time()
    while time.time() - t < timeout:
        d = client.get(path).json()
        job = d.get("job")
        if not job or job["state"] != "running":
            return d
        time.sleep(0.05)
    raise AssertionError(f"{path} did not finish")


def test_latest_wav_picks_newest_and_reads_its_record(tmp_path):
    assert latest_wav(tmp_path / "missing") is None
    assert latest_wav(tmp_path) is None
    old, new = tmp_path / "EP_1.wav", tmp_path / "EP_2.wav"
    old.write_bytes(b"a")
    new.write_bytes(b"bb")
    (tmp_path / "EP_3.mp3").write_bytes(b"c")
    os.utime(old, (1, 1))
    (tmp_path / "EP_2.json").write_text(json.dumps({"version": "v9"}), encoding="utf-8")
    wav, rec = latest_wav(tmp_path)
    assert wav == new and rec == {"version": "v9"}
    (tmp_path / "EP_2.json").write_text("{broken", encoding="utf-8")
    assert latest_wav(tmp_path)[1] == {}


def test_cover_path_stays_in_the_publish_folder(tmp_path):
    d = tmp_path / "publish"
    d.mkdir()
    (d / "cover.jpg").write_bytes(b"x")
    (tmp_path / "evil.jpg").write_bytes(b"x")
    assert cover_path({"cover": {"jpg": str(d / "cover.jpg")}}, d) == d / "cover.jpg"
    for doc in ({"cover": None}, {"cover": {"jpg": str(tmp_path / "evil.jpg")}}, {"cover": {"jpg": str(d / "gone.jpg")}}):
        try:
            cover_path(doc, d)
        except FileNotFoundError:
            continue
        raise AssertionError(doc)


def test_save_cover_copies_next_to_the_audio(tmp_path):
    src = tmp_path / "publish" / "cover.jpg"
    src.parent.mkdir()
    src.write_bytes(b"\xff\xd8\xffjpeg")
    exports = tmp_path / "exports" / "EP9"  # not there yet: an episode never exported
    out = save_cover(src, exports, "EP9")
    assert out == exports / "EP9_cover.jpg" and out.read_bytes() == src.read_bytes()
    src.write_bytes(b"\xff\xd8\xffnewer")
    assert save_cover(src, exports, "EP9").read_bytes() == b"\xff\xd8\xffnewer"
    assert sorted(p.name for p in exports.iterdir()) == ["EP9_cover.jpg"]  # no .tmp left behind
    assert src.is_file()


def test_upload_checklist_api(tmp_path):
    ws = Workspace(make_workspace(tmp_path / "ws"))
    pub = Publisher(ws, lambda: ClaudePublisher(client=FakePublishAnthropic()))
    posters = Posters(ws, pub, lambda: ClaudeDesigner(client=FakePosterAnthropic()))
    client = TestClient(create_app(ws.root, MockEditorAdapter(), web_dist=Path("/nonexistent"),
                                   publisher=pub, posters=posters))

    # nothing yet
    d = client.get(f"{EP}/upload").json()
    assert d == {"upload_page": UPLOAD_PAGE, "audio": None, "pack": None, "cover": None, "ready": False}
    assert client.get(f"{EP}/upload/cover.jpg").status_code == 404
    assert client.post(f"{EP}/upload/save-cover").status_code == 404

    # export the WAV, write the publish pack, choose a cover
    assert client.post(f"{EP}/export", json={"formats": ["wav"]}).status_code == 200
    assert wait(client, f"{EP}/export")["job"]["state"] == "done"
    client.post(f"{EP}/publish/generate")
    assert wait(client, f"{EP}/publish")["pack"] is not None
    client.post(f"{EP}/poster/generate")
    wait(client, f"{EP}/poster")
    client.post(f"{EP}/poster/v1/choose")
    assert wait(client, f"{EP}/poster")["cover"] is not None

    d = client.get(f"{EP}/upload").json()
    assert d["ready"] is True
    assert d["audio"]["name"].startswith(EPISODE) and d["audio"]["name"].endswith(".wav")
    assert d["audio"]["bytes"] > 0 and d["audio"]["stale"] is False and d["audio"]["exported_at"]
    assert d["pack"] == {"stale": False, "edited": False}
    assert d["cover"]["px"] == 3000 and d["cover"]["bytes"] > 0
    # the WAV downloads through the export route the page links to
    assert client.get(f"{EP}/exports/{d['audio']['name']}").status_code == 200

    r = client.get(f"{EP}/upload/cover.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert r.content[:3] == b"\xff\xd8\xff"
    assert quote(f"{EPISODE}_cover.jpg") in r.headers["content-disposition"]

    # 「下载封面」 also puts the cover next to the WAV in exports/<ep>/ (the publish/ copy stays)
    r = client.post(f"{EP}/upload/save-cover")
    assert r.status_code == 200
    out = Path(r.json()["path"])
    assert out == ws.root / "exports" / EPISODE / f"{EPISODE}_cover.jpg"
    assert r.json()["folder"] == str(out.parent) and r.json()["name"] == out.name
    assert out.read_bytes() == client.get(f"{EP}/upload/cover.jpg").content
    assert Path(client.get(f"{EP}/poster").json()["cover"]["jpg"]).is_file()
    # the WAV is still the newest audio, and saving again just replaces the copy
    assert client.get(f"{EP}/upload").json()["audio"]["name"].endswith(".wav")
    assert client.post(f"{EP}/upload/save-cover").status_code == 200
    assert sorted(p.name for p in out.parent.glob("*.jpg")) == [out.name]

    # a later edit makes the WAV and the show notes out of date
    client.post(f"{EP}/edits/e003/review", json={"action": "restore"})
    d = client.get(f"{EP}/upload").json()
    assert d["audio"]["stale"] is True and d["pack"]["stale"] is True and d["ready"] is False

    assert client.get("/api/episodes/NOPE/upload").status_code == 404
