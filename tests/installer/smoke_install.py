"""Real install → start → in-app update → broken update rolls back, on this machine (CI: Windows,
macOS, Linux). Uses the real installer scripts, uv, Python, packages and the ffmpeg download;
releases are built from this checkout into a local folder that stands in for GitHub Releases.

    python tests/installer/smoke_install.py [--keep]     # needs web/dist (npm run build)
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "installer"))
import build_release  # noqa: E402

PORT = 8791
WIN = sys.platform == "win32"
V1, V2, V3 = "2026.1.1.1", "2026.1.1.2", "2026.1.1.3"


def step(msg: str) -> None:
    print(f"\n=== {msg}", flush=True)


def api(path: str, method: str = "GET", timeout: float = 30) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method,
                                 data=b"" if method == "POST" else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def version() -> str | None:
    try:
        return api("/api/app", timeout=3)["version"]
    except OSError:
        return None


def wait(pred, what: str, timeout: float = 300) -> object:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(1)
    raise SystemExit(f"FAIL: timed out waiting for {what}")


def broken_repo(tmp: Path) -> Path:
    """A copy of this checkout whose app exits at once (a release that cannot start)."""
    r = tmp / "broken"
    for d in ("lacuna_core", "lacuna_app", "scripts", "installer"):
        shutil.copytree(REPO / d, r / d, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO / "web" / "dist", r / "web" / "dist")
    for f in ("pyproject.toml", "README.md"):
        shutil.copyfile(REPO / f, r / f)
    main = r / "lacuna_app" / "__main__.py"
    main.write_text("import sys\nsys.exit(3)\n" + main.read_text(encoding="utf-8"), encoding="utf-8")
    return r


def main() -> int:
    keep = "--keep" in sys.argv
    tmp = Path(tempfile.mkdtemp(prefix="lacuna-smoke-"))
    base, root, ws = tmp / "releases", tmp / "root", tmp / "ws"
    env = dict(os.environ, LACUNA_RELEASE_BASE=str(base), LACUNA_ROOT=str(root), LACUNA_WORKSPACE=str(ws),
               LACUNA_NO_START="1")
    for k in ("VIRTUAL_ENV", "UV_SYSTEM_PYTHON", "UV_PYTHON"):
        env.pop(k, None)
    proc = None
    try:
        step(f"build release {V1}")
        build_release.build(V1, base, notes="第一版")

        step("install with the real installer script")
        if WIN:
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO / "installer" / "install.ps1")]
        else:
            cmd = ["sh", str(REPO / "installer" / "install.sh")]
        t0 = time.monotonic()
        subprocess.run(cmd, env=env, check=True)
        print(f"install took {time.monotonic() - t0:.0f} s")
        cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
        assert cfg["current"] == V1 and Path(cfg["workspace"]) == ws, cfg
        if sys.platform == "darwin":
            assert (Path.home() / "Applications" / "LACUNA.app" / "Contents" / "MacOS" / "LACUNA").is_file()

        step("start via the launcher")
        py = root / "venv" / ("Scripts/python.exe" if WIN else "bin/python")
        cfg["port"] = PORT
        (root / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WIN else {"start_new_session": True}
        run_env = {k: v for k, v in env.items() if k != "PATH"} | {"PATH": os.environ.get("PATH", "")}
        if not WIN:
            # prove the app uses the bundled ffmpeg, not one the runner happens to have
            run_env["PATH"] = "/usr/bin:/bin"
        proc = subprocess.Popen([str(py), str(root / "lacuna_launcher.py"), "run", "--no-browser"], env=run_env, **kw)
        wait(lambda: version() == V1, f"{V1} to answer", 180)
        info = api("/api/app")
        print(json.dumps({k: info[k] for k in ("version", "installed", "platform", "ffmpeg", "ffprobe", "key")}, ensure_ascii=False))
        assert info["installed"], info
        for tool in ("ffmpeg", "ffprobe"):
            assert info[tool] and Path(info[tool]).resolve().parent == (root / "ffmpeg").resolve(), info
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=10) as r:
            assert b"<div id=\"root\"" in r.read(), "UI not served"
        assert api("/api/health")["ok"]

        def update_to(v: str) -> None:
            st = api("/api/app/update/check", "POST")["update"]
            assert st["available"] and st["latest"] == v, st
            api("/api/app/update/prepare", "POST")
            job = wait(lambda: (lambda j: j if j and j["state"] != "running" else None)(api("/api/app")["update"]["job"]),
                       "download", 120)
            assert job["state"] == "ready", job
            assert api("/api/app/update/apply", "POST")["restarting"]

        step(f"in-app update to {V2}")
        build_release.build(V2, base, notes="第二版")
        t0 = time.monotonic()
        update_to(V2)

        def logged(v: str):
            # the new version answers a moment before the launcher logs the update as done
            last = (api("/api/app")["update"]["last_update"] or {}) if version() else {}
            return last if last.get("to") == v else None
        last = wait(lambda: logged(V2), f"{V2} after the update", 300)
        print(f"update took {time.monotonic() - t0:.0f} s")
        assert last["ok"] and version() == V2, last

        step(f"broken release {V3} rolls back to {V2}")
        build_release.build(V3, base, notes="坏的", repo=broken_repo(tmp))
        update_to(V3)

        def rolled_back():
            v = version()
            last = (api("/api/app")["update"]["last_update"] or {}) if v else {}
            return v == V2 and last.get("to") == V3 and not last.get("ok")
        wait(rolled_back, "rollback", 300)
        print(api("/api/app")["update"]["last_update"]["message"])
        cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
        assert cfg["current"] == V2, cfg
        kept = sorted(p.name for p in (root / "versions").iterdir() if not p.name.startswith("."))
        assert kept == [V1, V2], kept        # the broken one is dropped, the earlier fallback stays
        print("\nOK: install, start, update and rollback all work")
        return 0
    finally:
        if proc and proc.poll() is None:
            if WIN:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
            else:
                os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(30)
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
