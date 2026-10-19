"""Version and settings (phase 7, D51; the desktop self-update is retired, decision desktop-retired):
/api/app reports the version and the work in progress, API key saving in a development checkout."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import appinfo, create_app, editor
from lacuna_app.editor import MockEditorAdapter

from .synth import make_workspace


@pytest.fixture
def ws(tmp_path):
    return make_workspace(tmp_path / "ws")


@pytest.fixture
def client(ws, monkeypatch):
    monkeypatch.delenv("LACUNA_CLOUD", raising=False)
    return TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))


def test_version_from_file(tmp_path):
    assert appinfo.current_version(tmp_path) == "dev"
    (tmp_path / "VERSION").write_text("0c50ac4abc\n")
    assert appinfo.current_version(tmp_path) == "0c50ac4abc"


def test_api_info(client, ws):
    info = client.get("/api/app").json()
    assert info["version"] == appinfo.current_version() and info["workspace"] == str(ws.resolve())
    assert info["key"]["present"] is False and info["busy"] == [] and "ffmpeg" in info
    assert info["cloud"] is False and not {"update", "installed", "home"} & set(info)


def test_busy_lists_running_export(ws, monkeypatch):
    """The cloud host's updater (deploy/host/lacuna-update) waits while /api/app lists work."""
    monkeypatch.delenv("LACUNA_CLOUD", raising=False)
    from lacuna_app import exporter
    init = exporter.Exporter.__init__

    def busy_init(self, *a, **kw):
        init(self, *a, **kw)
        self._running = "EP001"
    monkeypatch.setattr(exporter.Exporter, "__init__", busy_init)
    c = TestClient(create_app(ws, MockEditorAdapter(), web_dist=Path("/nonexistent")))
    assert c.get("/api/app").json()["busy"] == ["导出（EP001）"]


def test_update_routes_are_gone(client):
    for path in ("/api/app/update/check", "/api/app/update/prepare", "/api/app/update/apply"):
        assert client.post(path).status_code in (404, 405), path


def test_api_key_saved(client, monkeypatch):
    saved = []
    monkeypatch.setattr(editor, "save_api_key", lambda k: saved.append(k) or "keychain")
    r = client.post("/api/app/api-key", json={"key": "sk-ant-api03-" + "x" * 40})
    assert r.json() == {"saved": True, "where": "keychain"} and saved


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
