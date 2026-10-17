"""In-app version / update / settings (phase 7, D51): feed check, background download with sha256,
apply refused while work runs, restart codes, API key saving."""
import hashlib
import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import appinfo, create_app, editor
from lacuna_app.appinfo import RESTART_EXIT, UPDATE_EXIT, UpdateError, Updater
from lacuna_app.editor import MockEditorAdapter

from .synth import make_workspace


def make_feed(tmp: Path, version: str, sha: str | None = None, zip_version: str | None = None) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VERSION", (zip_version or version) + "\n")
        z.writestr("lacuna_app/__init__.py", "")
    data = buf.getvalue()
    d = tmp / "feed"
    d.mkdir(parents=True, exist_ok=True)
    (d / "lacuna.zip").write_bytes(data)
    (d / "version.json").write_text(json.dumps({"version": version, "zip": "lacuna.zip", "notes": "修了导出",
                                                 "sha256": sha or hashlib.sha256(data).hexdigest()}))
    return (d / "version.json").as_uri()


def test_dev_checkout_never_updates(tmp_path):
    u = Updater(home=None, feed_url=make_feed(tmp_path, "2099.1.1.1"), version="dev")
    st = u.check(force=True)
    assert not st["installed"] and not st["available"] and st["latest"] is None
    with pytest.raises(UpdateError):
        u.prepare()


def test_check_prepare_apply(tmp_path):
    home = tmp_path / "home"
    u = Updater(home=home, feed_url=make_feed(tmp_path, "2026.10.18.1"), version="2026.10.17.1")
    st = u.check()
    assert st["available"] and st["latest"] == "2026.10.18.1" and st["notes"] == "修了导出"
    with pytest.raises(UpdateError, match="还没下载好"):
        u.apply([], lambda code: None)
    st = u.prepare(wait=True)
    assert st["job"]["state"] == "ready", st
    assert (home / "versions" / "2026.10.18.1" / "VERSION").is_file()
    assert not list((home / "downloads").iterdir())
    with pytest.raises(UpdateError, match="导出（EP002）还没做完"):
        u.apply(["导出（EP002）"], lambda code: None)
    codes = []
    assert u.apply([], codes.append) == {"restarting": True, "version": "2026.10.18.1"}
    assert codes == [UPDATE_EXIT]
    assert json.loads((home / "pending.json").read_text())["version"] == "2026.10.18.1"


def test_same_or_older_feed_is_not_an_update(tmp_path):
    u = Updater(home=tmp_path / "h", feed_url=make_feed(tmp_path, "2026.10.17.1"), version="2026.10.17.1")
    assert not u.check()["available"]
    with pytest.raises(UpdateError, match="最新"):
        u.prepare()


def test_bad_checksum_or_version_mismatch(tmp_path):
    u = Updater(home=tmp_path / "h", feed_url=make_feed(tmp_path, "2026.10.18.1", sha="0" * 64), version="2026.10.17.1")
    u.check()
    st = u.prepare(wait=True)
    assert st["job"]["state"] == "error" and "校验" in st["job"]["error"]
    assert not (tmp_path / "h" / "versions" / "2026.10.18.1").exists()
    u2 = Updater(home=tmp_path / "h2", feed_url=make_feed(tmp_path / "b", "2026.10.18.1", zip_version="2026.1.1.1"),
                 version="2026.10.17.1")
    u2.check()
    st = u2.prepare(wait=True)
    assert st["job"]["state"] == "error" and "对不上" in st["job"]["error"]


def test_offline_check_keeps_working(tmp_path):
    u = Updater(home=tmp_path / "h", feed_url=(tmp_path / "missing.json").as_uri(), version="2026.10.17.1")
    st = u.check()
    assert st["error"].startswith("检查更新失败") and not st["available"]


def test_last_update_from_launcher_log(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    (home / "update_log.json").write_text(json.dumps({"last": {"ok": False, "message": "已自动回到 1"}}))
    assert Updater(home=home, feed_url="x", version="2").status()["last_update"]["message"] == "已自动回到 1"


# ---------------------------------------------------------------------------- API

@pytest.fixture
def ws(tmp_path):
    return make_workspace(tmp_path / "ws")


def client_for(ws, updater, restarts):
    app = create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent"), updater=updater, restart=restarts.append)
    return TestClient(app)


def test_api_info_and_update_flow(tmp_path, ws, monkeypatch):
    monkeypatch.setattr(appinfo.threading, "Timer", lambda delay, fn: type("T", (), {"start": lambda self: fn()})())
    u = Updater(home=tmp_path / "home", feed_url=make_feed(tmp_path, "2026.10.18.1"), version="2026.10.17.1")
    restarts = []
    c = client_for(ws, u, restarts)
    info = c.get("/api/app").json()
    assert info["version"] == "2026.10.17.1" and info["installed"] and info["workspace"] == str(ws.resolve())
    assert info["key"]["present"] is False and info["busy"] == [] and "ffmpeg" in info
    assert c.post("/api/app/update/check").json()["update"]["available"]
    c.post("/api/app/update/prepare")
    for _ in range(100):
        if c.get("/api/app").json()["update"]["job"]["state"] != "running":
            break
        time.sleep(0.05)
    r = c.post("/api/app/update/apply")
    assert r.status_code == 200 and r.json()["restarting"]
    assert restarts == [UPDATE_EXIT]


def test_api_apply_refused_while_exporting(tmp_path, ws, monkeypatch):
    u = Updater(home=tmp_path / "home", feed_url=make_feed(tmp_path, "2026.10.18.1"), version="2026.10.17.1")
    u.check()
    u.prepare(wait=True)
    from lacuna_app import exporter
    init = exporter.Exporter.__init__

    def busy_init(self, *a, **kw):
        init(self, *a, **kw)
        self._running = "EP001"
    monkeypatch.setattr(exporter.Exporter, "__init__", busy_init)
    restarts = []
    c = client_for(ws, u, restarts)
    r = c.post("/api/app/update/apply")
    assert r.status_code == 409 and "导出（EP001）" in r.json()["detail"]
    assert restarts == []


def test_api_key_saved_and_restart(tmp_path, ws, monkeypatch):
    monkeypatch.setattr(appinfo.threading, "Timer", lambda delay, fn: type("T", (), {"start": lambda self: fn()})())
    saved = []
    monkeypatch.setattr(editor, "save_api_key", lambda k: saved.append(k) or "keychain")
    restarts = []
    c = client_for(ws, Updater(home=tmp_path / "home", feed_url="x", version="2026.10.17.1"), restarts)
    r = c.post("/api/app/api-key", json={"key": "sk-ant-api03-" + "x" * 40})
    assert r.json() == {"saved": True, "where": "keychain", "restarting": True}
    assert restarts == [RESTART_EXIT] and saved
    # a dev checkout does not restart itself
    restarts.clear()
    c = client_for(ws, Updater(home=None, feed_url="x", version="dev"), restarts)
    assert c.post("/api/app/api-key", json={"key": "sk-ant-api03-" + "x" * 40}).json()["restarting"] is False
    assert restarts == []


def test_save_api_key_validates_and_writes_file(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        editor.save_api_key("short")
    if editor.sys.platform in ("win32", "darwin"):
        pytest.skip("writes the registry / Keychain there")
    monkeypatch.setenv("LACUNA_HOME", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "old")
    assert editor.save_api_key(" sk-ant-api03-" + "y" * 40 + " ") == "file"
    f = tmp_path / "api_key"
    assert f.read_text() == "sk-ant-api03-" + "y" * 40 and (f.stat().st_mode & 0o777) == 0o600
    assert "ANTHROPIC_API_KEY" not in editor.os.environ
