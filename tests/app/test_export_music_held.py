"""An export uses the music as it was when it started (batch 8 regression, EG-12): music changed while it runs
goes into the next export and marks this one out of date."""
import json
import threading
from pathlib import Path

from fastapi.testclient import TestClient

from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter

from .synth import EPISODE, make_workspace, write_music
from .test_music_api import _wait_export, upload

EP = f"/api/episodes/{EPISODE}"


def test_music_changed_after_the_export_started_is_not_in_it(tmp_path, monkeypatch):
    client = TestClient(create_app(make_workspace(tmp_path / "ws"), MockEditorAdapter(), web_dist=Path("/nonexistent")))
    aid = upload(client, write_music(tmp_path / "in" / "intro.wav", 6.0), "intro").json()["asset"]["id"]
    pid = client.post(f"{EP}/music", json={"asset_id": aid, "role": "intro", "solo_s": 4}).json()["placements"][0]["id"]

    # hold the export's thread until the intro has been taken out
    started, real = [], threading.Thread.start
    monkeypatch.setattr(threading.Thread, "start", lambda self: started.append(self) if self.name.startswith("export-") else real(self))
    assert client.post(f"{EP}/export", json={"formats": ["wav"]}).status_code == 200
    assert client.delete(f"{EP}/music/{pid}").status_code == 200
    monkeypatch.setattr(threading.Thread, "start", real)
    started[0].start()

    job = _wait_export(client)
    rec = json.loads(next((tmp_path / "ws" / "exports" / EPISODE).glob("*.json")).read_text("utf-8"))
    assert [c["role"] for c in rec["music"]] == ["intro"]      # the music of the moment it started
    assert job["music_stale"] is True                          # and it says the music changed since
