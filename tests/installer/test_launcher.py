"""Installer / launcher / release builder (phase 7, D51), without network, uv or a real app:
uv is a fake runner, the app is tests/installer/fake_app.py."""
import importlib.util
import json
import shutil
import socket
import sys
import threading
import time
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


L = load("lacuna_launcher", REPO / "installer" / "lacuna_launcher.py")
B = load("build_release", REPO / "installer" / "build_release.py")
FAKE_APP = Path(__file__).with_name("fake_app.py")


def fake_repo(tmp: Path) -> Path:
    r = tmp / "repo"
    for d in ("lacuna_core", "lacuna_app", "scripts"):
        (r / d).mkdir(parents=True)
        (r / d / "__init__.py").write_text("")
    (r / "lacuna_app" / "__pycache__").mkdir()
    (r / "lacuna_app" / "__pycache__" / "x.pyc").write_bytes(b"x")
    shutil.copytree(REPO / "installer", r / "installer", ignore=shutil.ignore_patterns("__pycache__"))
    (r / "web" / "dist" / "assets").mkdir(parents=True)
    (r / "web" / "dist" / "index.html").write_text("<html></html>")
    (r / "web" / "dist" / "assets" / "app.js").write_text("1")
    (r / "pyproject.toml").write_text("[project]\nname='x'\n")
    (r / "README.md").write_text("x")
    return r


def release(tmp: Path, version: str, out: Path | None = None) -> Path:
    out = out or tmp / f"dist-{version}"
    B.build(version, out, notes=f"版本 {version}", repo=fake_repo(tmp / version))
    return out


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeUv:
    """Records uv calls; `uv venv` creates the venv's python; `pip install -e <dir>` fails when the
    folder holds NOPIP."""
    def __init__(self, root: Path):
        self.root, self.calls = root, []

    def __call__(self, cmd, env=None, cwd=None):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        if cmd[1] == "venv":
            py = L.venv_python(self.root)
            py.parent.mkdir(parents=True, exist_ok=True)
            py.write_text("")
        if cmd[1:3] == ["pip", "install"]:
            target = Path(cmd[-1].split("[")[0])
            return 1 if (target / "NOPIP").exists() else 0
        return 0

    def installs(self):
        return [Path(c[-1].split("[")[0]).name for c in self.calls if c[1:3] == ["pip", "install"]]


@pytest.fixture
def root(tmp_path, monkeypatch):
    r = tmp_path / "LACUNA"
    L.uv_path(r).parent.mkdir(parents=True)
    L.uv_path(r).write_text("")
    monkeypatch.setattr(L, "ensure_ffmpeg", lambda root: L.ffmpeg_dir(root))
    return r


# ---------------------------------------------------------------------------- release builder

def test_build_release_zip_and_feed(tmp_path):
    out = release(tmp_path, "2026.10.17.1")
    feed = json.loads((out / "version.json").read_text(encoding="utf-8"))
    assert feed["version"] == "2026.10.17.1" and feed["zip"] == "lacuna.zip" and feed["notes"] == "版本 2026.10.17.1"
    names = set(zipfile.ZipFile(out / "lacuna.zip").namelist())
    assert {"VERSION", "pyproject.toml", "web/dist/index.html", "web/dist/assets/app.js",
            "installer/lacuna_launcher.py", "lacuna_app/__init__.py"} <= names
    assert not any("__pycache__" in n for n in names)
    for f in ("lacuna_launcher.py", "install.sh", "install.ps1", "LACUNA-Setup.cmd"):
        assert (out / f).is_file()
    B.build("2026.10.17.2", tmp_path / "gh", url_base="https://x/releases/download/v2026.10.17.2/",
            repo=fake_repo(tmp_path / "gh-repo"))
    assert json.loads((tmp_path / "gh" / "version.json").read_text())["zip"] == \
        "https://x/releases/download/v2026.10.17.2/lacuna.zip"


def test_build_release_needs_ui_and_numeric_version(tmp_path):
    r = fake_repo(tmp_path)
    with pytest.raises(SystemExit):
        B.build("v1", tmp_path / "o", repo=r)
    shutil.rmtree(r / "web" / "dist")
    with pytest.raises(SystemExit):
        B.build("2026.1.1.1", tmp_path / "o", repo=r)


def test_version_order():
    assert L.version_key("2026.10.17.10") > L.version_key("2026.10.17.9") > L.version_key("2026.9.30.1")
    assert L.version_key("dev") == ()


# ---------------------------------------------------------------------------- install

def test_install_from_feed_writes_config_and_keeps_workspace(tmp_path, root):
    base = release(tmp_path, "2026.10.17.1")
    ws = tmp_path / "ws"
    uv = FakeUv(root)
    cfg = L.install(root, str(base), ws, None, None, shortcuts=False, runner=uv)
    assert cfg["current"] == "2026.10.17.1" and cfg["port"] == 8765 and cfg["workspace"] == str(ws)
    assert (root / "versions" / "2026.10.17.1" / "web" / "dist" / "index.html").is_file()
    assert (root / "lacuna_launcher.py").is_file() and (root / ("LACUNA.cmd" if L.WINDOWS else "LACUNA.command")).is_file()
    assert uv.installs() == ["2026.10.17.1"]
    assert cfg["feed"].endswith("/version.json") and cfg["feed"].startswith("file:")

    # reinstall a newer release: workspace and port stay, previous is remembered, older pruned
    base2 = release(tmp_path, "2026.10.18.1")
    cfg2 = L.install(root, str(base2), None, None, None, shortcuts=False, runner=uv)
    assert cfg2["workspace"] == str(ws) and cfg2["current"] == "2026.10.18.1" and cfg2["previous"] == "2026.10.17.1"
    base3 = release(tmp_path, "2026.10.19.1")
    L.install(root, str(base3), None, None, None, shortcuts=False, runner=uv)
    assert sorted(p.name for p in (root / "versions").iterdir()) == ["2026.10.18.1", "2026.10.19.1"]


def test_install_rejects_bad_download(tmp_path, root):
    base = release(tmp_path, "2026.10.17.1")
    feed = json.loads((base / "version.json").read_text())
    feed["sha256"] = "0" * 64
    (base / "version.json").write_text(json.dumps(feed))
    with pytest.raises(L.LauncherError, match="校验"):
        L.install(root, str(base), tmp_path / "ws", None, None, shortcuts=False, runner=FakeUv(root))
    assert not (root / "config.json").exists()


def test_install_without_uv_explains(tmp_path):
    with pytest.raises(L.LauncherError, match="uv"):
        L.install(tmp_path / "empty", "x", tmp_path / "ws", None, None, shortcuts=False)


@pytest.mark.skipif(sys.platform != "darwin", reason="LACUNA.app is macOS only")
def test_mac_app_bundle(tmp_path, root):
    made = L.make_shortcuts(root, 8765, home=tmp_path)
    app = tmp_path / "Applications" / "LACUNA.app"
    assert made == [app]
    exe = app / "Contents" / "MacOS" / "LACUNA"
    assert exe.stat().st_mode & 0o111 and "open -a Terminal" in exe.read_text()


# ---------------------------------------------------------------------------- run: update + rollback

def stage(root: Path, tmp: Path, version: str, broken: bool = False) -> None:
    """What the app's `prepare` leaves behind: an unpacked version folder."""
    d = root / "versions" / version
    d.mkdir(parents=True)
    (d / "VERSION").write_text(version)
    if broken:
        (d / "BROKEN").write_text("")


def wait_for(pred, timeout=20.0, root: Path | None = None, port: int | None = None):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(0.05)
    detail = ""
    if root is not None and (root / "fake_app.log").exists():
        detail += "\nfake_app.log:\n" + (root / "fake_app.log").read_text()
    if port is not None:
        import urllib.request
        try:
            detail += "\nGET: " + urllib.request.urlopen(f"http://127.0.0.1:{port}/api/app", timeout=3).read().decode()
        except Exception as e:  # noqa: BLE001
            detail += f"\nGET failed: {e!r}"
    raise AssertionError("timed out" + detail)


def test_run_update_then_rollback(tmp_path, root, monkeypatch):
    port = free_port()
    base = release(tmp_path, "2026.10.17.1")
    uv = FakeUv(root)
    L.install(root, str(base), tmp_path / "ws", port, None, shortcuts=False, runner=uv)
    monkeypatch.setattr(L, "server_cmd", lambda r, cfg, browser: [sys.executable, FAKE_APP, cfg["port"], r])
    monkeypatch.setattr(L.webbrowser, "open", lambda url: None)
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("code", L.run(root, runner=uv, health_timeout=15)))
    t.start()
    try:
        version = lambda: (L.health(port) or {}).get("version")
        wait_for(lambda: version() == "2026.10.17.1", root=root, port=port)

        # 1. a good update: the app wrote pending.json and exited 75
        stage(root, tmp_path, "2026.10.18.1")
        L.write_json(root / "pending.json", {"version": "2026.10.18.1"})
        (root / "control").write_text("75")
        wait_for(lambda: version() == "2026.10.18.1")
        log = wait_for(lambda: (L.read_json(root / "update_log.json") or {}).get("last"))
        assert log["ok"] and log["to"] == "2026.10.18.1"
        cfg = L.load_config(root)
        assert cfg["current"] == "2026.10.18.1" and cfg["previous"] == "2026.10.17.1"

        # 2. a release that cannot start: back to the previous version by itself
        stage(root, tmp_path, "2026.10.19.1", broken=True)
        L.write_json(root / "pending.json", {"version": "2026.10.19.1"})
        (root / "control").write_text("75")
        wait_for(lambda: (L.read_json(root / "update_log.json") or {}).get("last", {}).get("to") == "2026.10.19.1")
        wait_for(lambda: version() == "2026.10.18.1")
        log = L.read_json(root / "update_log.json")["last"]
        assert not log["ok"] and "回到 2026.10.18.1" in log["message"]
        cfg = L.load_config(root)
        assert cfg["current"] == "2026.10.18.1" and cfg["previous"] == "2026.10.17.1"
        assert not (root / "versions" / "2026.10.19.1").exists()
        assert uv.installs()[-2:] == ["2026.10.19.1", "2026.10.18.1"]

        # 3. packages of an update fail to install: stays on the running version
        stage(root, tmp_path, "2026.10.20.1")
        (root / "versions" / "2026.10.20.1" / "NOPIP").write_text("")
        L.write_json(root / "pending.json", {"version": "2026.10.20.1"})
        (root / "control").write_text("75")
        wait_for(lambda: "没装上" in ((L.read_json(root / "update_log.json") or {}).get("last") or {}).get("message", ""))
        wait_for(lambda: version() == "2026.10.18.1")

        # 4. plain restart (new API key), then quit
        (root / "control").write_text("76")
        time.sleep(0.3)
        wait_for(lambda: version() == "2026.10.18.1")
        # a second start while it runs only opens the browser
        assert L.run(root, browser=False) == 0
        (root / "control").write_text("0")
        t.join(20)
        assert result["code"] == 0
    finally:
        if t.is_alive():
            (root / "control").write_text("0")
            t.join(20)
