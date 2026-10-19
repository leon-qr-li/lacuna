"""Moving the desktop workspace to the cloud (lacuna_app/migrate.py, routes/migrate.py)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lacuna_app import Episode, Workspace, create_app, migrate, totp
from lacuna_app.editor import MockEditorAdapter
from tests.app.e2e.auth import FakeMailer

from .synth import EPISODE, make_workspace
from .test_cloud import PW, hdr, keys, token, verifier  # noqa: F401  (fixtures)

DESK = r"C:\Projects\LACUNA_Workspace"


def desktop_copy(tmp_path) -> dict[str, bytes]:
    """A desktop workspace as the browser reads it: every file, with Windows paths inside the JSON."""
    src = make_workspace(tmp_path / "desk")
    (src / "models").mkdir()
    (src / "models" / "big.onnx").write_bytes(b"model")
    (src / "Thumbs.db").write_bytes(b"x")
    out = {}
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(src).as_posix()
        data = p.read_bytes()
        if p.suffix == ".json" or p.name.endswith(".json.bak"):
            text = data.decode("utf-8")
            esc = json.dumps(str(src))[1:-1]
            # every absolute path under the desktop root becomes C:\Projects\LACUNA_Workspace\…
            while esc in text:
                i = text.index(esc)
                j = text.index('"', i)
                win = DESK + text[i + len(esc):j].replace("/", "\\")
                text = text[:i] + json.dumps(win)[1:-1] + text[j:]
            data = text.encode("utf-8")
        out[rel] = data
    return out


@pytest.fixture
def restarts():
    return []


def signed_in(app, keys):  # noqa: F811
    """The owner, through Access and the two-step sign-in."""
    c = TestClient(app, base_url="https://testserver")
    c.headers.update(hdr(token(keys[0])))
    r = c.post("/api/auth/register", json={"email": "leon@example.com", "password": PW})
    code = totp.code_at(r.json()["secret"], int(time.time() // totp.STEP))
    assert c.post("/api/auth/2fa/enroll", json={"ticket": r.json()["ticket"], "code": code}).status_code == 200
    return c


@pytest.fixture
def make_cloud(tmp_path, monkeypatch, verifier, keys, restarts):  # noqa: F811
    monkeypatch.setenv("LACUNA_CLOUD", "1")
    monkeypatch.setenv("LACUNA_OWNER_EMAIL", "leon@example.com")

    def make(**services):
        app = create_app(tmp_path / "ws", MockEditorAdapter(), web_dist=tmp_path / "none", mailer=FakeMailer(),
                         access_verifier=verifier, restart=restarts.append, **services)
        return signed_in(app, keys)
    return make


@pytest.fixture
def cloud(make_cloud):
    return make_cloud()


def send(c, rel, data):
    return c.post("/api/migrate/file", params={"path": rel}, content=data,
                  headers={"content-type": "application/octet-stream"})


def test_paths_are_cleaned_and_server_folders_skipped():
    assert migrate.clean_path("episodes\\EP1\\state.json") == "episodes/EP1/state.json"
    assert migrate.clean_path("/library/a.mp3") == "library/a.mp3"
    for skipped in ("auth/users.json", "spaces/x/a", "models/m.onnx", "tmp/x", "episodes/Thumbs.db", ".DS_Store"):
        assert migrate.clean_path(skipped) is None, skipped
    for bad in ("", "../etc/passwd", "episodes/../../x", "a/b:c", "a/ b", "a\x00b"):
        with pytest.raises(migrate.MigrateError):
            migrate.clean_path(bad)


def test_remap_turns_desktop_paths_into_server_paths(tmp_path):
    data = {"media": [{"path": DESK.lower() + r"\episodes\EP1\media\Leon.wav"}], "title": "C:\\elsewhere", "n": 3}
    new = migrate.remap(data, [DESK], tmp_path)
    assert new["media"][0]["path"] == str(tmp_path / "episodes/EP1/media/Leon.wav")
    assert new["title"] == "C:\\elsewhere" and new["n"] == 3
    assert migrate.remap(DESK + "_old\\x", [DESK], tmp_path) == DESK + "_old\\x"     # not inside the root


def test_owner_moves_the_desktop_workspace(cloud, tmp_path, restarts):
    files = desktop_copy(tmp_path)
    assert "models/big.onnx" in files and "Thumbs.db" in files
    assert cloud.get("/api/migrate").json() == {"staged": {}, "episodes": 0}
    for rel, data in files.items():
        r = send(cloud, rel, data)
        assert r.status_code == 200, (rel, r.text)
    staged = cloud.get("/api/migrate").json()["staged"]
    assert "models/big.onnx" not in staged and "Thumbs.db" not in staged
    kept = {k: v for k, v in files.items() if migrate.clean_path(k)}
    assert staged == {k: len(v) for k, v in kept.items()}
    # the browser's count must match what arrived
    r = cloud.post("/api/migrate/finish", json={"files": len(kept) + 1, "bytes": sum(map(len, kept.values()))})
    assert r.status_code == 422 and restarts == []
    r = cloud.post("/api/migrate/finish", json={"files": len(kept), "bytes": sum(map(len, kept.values()))})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["restarting"] and out["episodes"] == 1 and out["rewritten"] >= 1
    root = cloud.app.state.workspace.root
    assert not (root / "tmp" / "migrate").exists()
    state = (root / "episodes" / EPISODE / "state.json").read_text(encoding="utf-8")
    assert "C:\\\\Projects" not in state and str(root) in state
    ep = Episode(Workspace(root), EPISODE)           # the moved episode opens with its audio on the server
    assert all(Path(m.path).is_file() for m in ep.media.values())
    time.sleep(0.8)
    assert restarts == [76]


def test_resend_and_cancel(cloud):
    assert send(cloud, "library/a.mp3", b"abc").json() == {"size": 3}
    assert send(cloud, "library/a.mp3", b"abcd").json() == {"size": 4}      # resent: replaced
    assert send(cloud, "auth/users.json", b"{}").json() == {"skipped": True}
    assert send(cloud, "../x", b"x").status_code == 422
    assert cloud.post("/api/migrate/file", params={"path": "library/b"}, content=b"x").status_code == 415
    assert cloud.get("/api/migrate").json()["staged"] == {"library/a.mp3": 4}
    assert cloud.post("/api/migrate/cancel").status_code == 200
    assert cloud.get("/api/migrate").json()["staged"] == {}


def test_a_folder_that_is_not_a_workspace_is_refused(cloud, restarts):
    send(cloud, "photos/a.jpg", b"jpg")
    r = cloud.post("/api/migrate/finish", json={"files": 1, "bytes": 3})
    assert r.status_code == 422 and "LACUNA_Workspace" in r.json()["detail"] and restarts == []


def test_not_while_importing_or_exporting(make_cloud, tmp_path):
    from lacuna_app.importer import Importer
    importer = Importer(Workspace(tmp_path / "ws").ensure(), models_dir=tmp_path / "models")
    importer._running = "EP9"
    cloud = make_cloud(importer=importer)
    send(cloud, "library/a.mp3", b"abc")
    r = cloud.post("/api/migrate/finish", json={"files": 1, "bytes": 3})
    assert r.status_code == 409
    assert cloud.get("/api/migrate").json()["staged"] == {"library/a.mp3": 3}       # nothing moved


def test_only_the_owner_and_only_in_the_cloud(tmp_path, monkeypatch, cloud, keys):  # noqa: F811
    other = TestClient(cloud.app, base_url="https://testserver")
    other.headers.update(hdr(token(keys[0], email="pei@example.com")))
    assert other.get("/api/migrate").status_code in (401, 403)
    monkeypatch.delenv("LACUNA_CLOUD")
    desk = TestClient(create_app(tmp_path / "desk", MockEditorAdapter(), web_dist=tmp_path / "none"))
    assert desk.get("/api/migrate").status_code == 404
