"""App version, in-app updates and settings (phase 7, D51).

The installed app runs under `installer/lacuna_launcher.py`, which sets `LACUNA_HOME` (the install
root) and `LACUNA_UPDATE_FEED` (the release feed, `version.json`). An update happens in two steps:

1. `prepare`: download the release zip in the background, check its sha256 against the feed,
   unpack it to `<home>/versions/<version>/`. The running app is untouched.
2. `apply`: refused while an import, export or publish pack is running; otherwise write
   `<home>/pending.json` and ask the server to stop with exit code 75. The launcher installs the
   new version's packages, starts it, and goes back to the previous version if it does not come up.

A development checkout (no `LACUNA_HOME`) reports version "dev" and never updates itself.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from .store import atomic_write_json, read_json
from .i18n import join_list, tr

APP_ROOT = Path(__file__).resolve().parent.parent      # the version folder (or the git checkout)
UPDATE_EXIT = 75     # keep in sync with installer/lacuna_launcher.py
RESTART_EXIT = 76
CHECK_TTL = 30 * 60


class UpdateError(RuntimeError):
    pass


def current_version(app_root: Path = APP_ROOT) -> str:
    try:
        return (app_root / "VERSION").read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"


def version_key(v: str | None) -> tuple:
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return ()


def _fetch(url: str, timeout: float = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "LACUNA"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _resolve(feed_url: str, name: str) -> str:
    return name if "://" in name else urllib.parse.urljoin(feed_url, urllib.parse.quote(name))


class Updater:
    def __init__(self, home: str | Path | None = None, feed_url: str | None = None,
                 version: str | None = None):
        home = home if home is not None else os.environ.get("LACUNA_HOME")
        self.home = Path(home) if home else None
        self.feed_url = feed_url or os.environ.get("LACUNA_UPDATE_FEED") or \
            "https://github.com/leon-qr-li/lacuna/releases/latest/download/version.json"
        self.version = version or current_version()
        self._lock = threading.Lock()
        self._feed: dict | None = None
        self._checked = 0.0
        self._check_error: str | None = None
        self._checking = False
        self.job: dict | None = None            # prepare: {state, progress, version, error}

    @property
    def installed(self) -> bool:
        return self.home is not None and self.version != "dev"

    # ---- status
    def last_update(self) -> dict | None:
        if not self.home:
            return None
        f = self.home / "update_log.json"
        try:
            return read_json(f).get("last") if f.is_file() else None
        except (OSError, ValueError):
            return None

    def status(self) -> dict:
        with self._lock:
            feed, job, err, checked = self._feed, dict(self.job) if self.job else None, self._check_error, self._checked
        latest = feed.get("version") if feed else None
        return {"installed": self.installed, "version": self.version, "latest": latest,
                "available": bool(self.installed and latest and version_key(latest) > version_key(self.version)),
                "notes": (feed or {}).get("notes", ""), "published": (feed or {}).get("published"),
                "checked": checked or None, "error": err, "job": job, "last_update": self.last_update()}

    # ---- check
    def stale(self) -> bool:
        with self._lock:
            return time.time() - self._checked >= CHECK_TTL

    def begin_check(self) -> bool:
        """Claim the next background check (False when one is already under way)."""
        with self._lock:
            if self._checking:
                return False
            self._checking = True
            return True

    def check(self, force: bool = False) -> dict:
        if not self.installed:
            return self.status()
        with self._lock:
            fresh = self._feed is not None and time.time() - self._checked < CHECK_TTL
        if force or not fresh:
            try:
                feed = json.loads(_fetch(self.feed_url))
                if not feed.get("version") or not feed.get("zip") or not feed.get("sha256"):
                    raise ValueError("incomplete feed")
                err = None
            except (OSError, ValueError) as e:
                feed, err = None, tr("检查更新失败：{e}", e=e)
            with self._lock:
                self._checked = time.time()
                self._checking = False
                self._check_error = err
                if feed:
                    self._feed = feed
        return self.status()

    # ---- prepare (download + verify + unpack)
    def prepared(self, version: str) -> bool:
        return bool(self.home and (self.home / "versions" / version / "VERSION").is_file())

    def prepare(self, wait: bool = False) -> dict:
        if not self.installed:
            raise UpdateError(tr("开发版不能在 App 里更新"))
        st = self.status()
        if not st["available"]:
            raise UpdateError(tr("已经是最新版本"))
        with self._lock:
            if self.job and self.job["state"] == "running":
                return dict(self.job)
            feed = dict(self._feed)
            self.job = {"state": "running", "version": feed["version"], "progress": 0.0, "error": None}
        t = threading.Thread(target=self._prepare, args=(feed,), daemon=True)
        t.start()
        if wait:
            t.join()
        return self.status()

    def _set_job(self, **kw) -> None:
        with self._lock:
            self.job = (self.job or {}) | kw

    def _prepare(self, feed: dict) -> None:
        version = feed["version"]
        try:
            if not self.prepared(version):
                self._download_and_unpack(feed)
            self._set_job(state="ready", progress=1.0)
        except Exception as e:      # noqa: BLE001 - shown to Leon, the app keeps running
            self._set_job(state="error", error=tr("下载新版本失败：{e}", e=e))

    def _download_and_unpack(self, feed: dict) -> None:
        version = feed["version"]
        dl = self.home / "downloads"
        dl.mkdir(parents=True, exist_ok=True)
        part = dl / f"lacuna-{version}.zip.part"
        h = hashlib.sha256()
        req = urllib.request.Request(_resolve(self.feed_url, feed["zip"]), headers={"User-Agent": "LACUNA"})
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or feed.get("size") or 0)
            done = 0
            while chunk := r.read(1 << 20):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if total:
                    self._set_job(progress=min(0.95, done / total * 0.95))
        if h.hexdigest() != str(feed["sha256"]).lower():
            part.unlink(missing_ok=True)
            raise UpdateError(tr("文件校验不对，可能没下完整，再试一次"))
        versions = self.home / "versions"
        tmp = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=versions if versions.is_dir() else None))
        try:
            with zipfile.ZipFile(part) as z:
                if z.read("VERSION").decode().strip() != version:
                    raise UpdateError(tr("更新包的版本号和说明对不上"))
                z.extractall(tmp)
            versions.mkdir(parents=True, exist_ok=True)
            dst = versions / version
            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            os.replace(tmp, dst)
        finally:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
            part.unlink(missing_ok=True)

    # ---- apply
    def apply(self, busy: list[str], restart: Callable[[int], None]) -> dict:
        if not self.installed:
            raise UpdateError(tr("开发版不能在 App 里更新"))
        if busy:
            raise UpdateError(tr("{tasks}还没做完，做完再更新", tasks=join_list(busy)))
        with self._lock:
            job = dict(self.job) if self.job else None
        if not job or job.get("state") != "ready" or not self.prepared(job["version"]):
            raise UpdateError(tr("新版本还没下载好"))
        atomic_write_json(self.home / "pending.json", {"version": job["version"], "from": self.version,
                                                        "at": time.strftime("%Y-%m-%d %H:%M:%S")})
        restart(UPDATE_EXIT)
        return {"restarting": True, "version": job["version"]}


# ---------------------------------------------------------------------------- environment

def ffmpeg_status() -> dict:
    return {"ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe")}


def platform_name() -> str:
    return {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, sys.platform)


# ---------------------------------------------------------------------------- API

class KeyBody(BaseModel):
    key: str = Field(..., max_length=500)


def register(app, updater: Updater, workspace: Path, busy: Callable[[], list[str]],
             key_status: Callable[[], dict], models_ready: Callable[[], bool]) -> None:
    """/api/app*: version + update + settings. `app.state.restart(code)` stops the server with
    that exit code (set by __main__; tests replace it)."""
    from fastapi import HTTPException

    from . import editor
    from .cloud import enabled as cloud_enabled

    def restart_later(code: int) -> None:
        # answer the request first, then stop
        threading.Timer(0.3, lambda: app.state.restart(code)).start()

    def check_soon() -> None:
        """Keep the update status fresh without making a page wait on the network."""
        if updater.installed and updater.stale() and updater.begin_check():
            threading.Thread(target=updater.check, kwargs={"force": True}, daemon=True).start()

    check_soon()

    def info() -> dict:
        check_soon()
        return {"version": updater.version, "installed": updater.installed, "platform": platform_name(),
                "workspace": str(workspace), "home": str(updater.home) if updater.home else None,
                "update": updater.status(), "key": key_status(), "models": models_ready(),
                "busy": busy(), "cloud": cloud_enabled()} | ffmpeg_status()

    @app.get("/api/app")
    def app_info():
        return info()

    @app.post("/api/app/update/check")
    def update_check():
        updater.check(force=True)
        return info()

    @app.post("/api/app/update/prepare")
    def update_prepare():
        try:
            updater.prepare()
        except UpdateError as e:
            raise HTTPException(400, str(e))
        return info()

    @app.post("/api/app/update/apply")
    def update_apply():
        try:
            return updater.apply(busy(), restart_later)
        except UpdateError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/app/api-key")
    def set_key(body: KeyBody):
        try:
            where = editor.save_api_key(body.key)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except OSError as e:
            raise HTTPException(500, str(e))
        # the AI clients are made at startup: the installed app restarts itself (launcher), a dev
        # checkout has to be restarted by hand
        restarting = updater.installed and not busy()
        if restarting:
            restart_later(RESTART_EXIT)
        return {"saved": True, "where": where, "restarting": restarting}
