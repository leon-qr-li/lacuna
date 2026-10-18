"""Background export jobs: master the current version of an episode to WAV/MP3.

Exports go to ``<workspace>/exports/<episode_id>/<episode_id>_<timestamp>.{wav,mp3,json}``; the
JSON is the export record (which edits were applied, loudness report) so every delivered
version can be traced back to its recipe. One export runs at a time (CPU bound; the preview
keeps working because the job uses its own file handles).
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from lacuna_core.export import FORMATS, export, timeline_source
from lacuna_core.master import MasterSettings

from . import declip
from .episode import Episode
from .music import EpisodeMusic, credits
from .store import Workspace, atomic_write_json, check_id, inside
from .i18n import tr

DEFAULT_SHOW = "洛城二三事"  # i18n-ignore
FILE_SUFFIXES = (".wav", ".mp3", ".json")


class ExportBusy(RuntimeError):
    pass


class Exporter:
    def __init__(self, ws: Workspace):
        self.ws = ws
        self.jobs: dict[str, dict] = {}        # episode id -> latest job
        self._lock = threading.Lock()
        self._running: str | None = None
        self.on_done: list[Callable[[Episode], None]] = []   # e.g. chat learning; must not raise

    def dir_for(self, episode_id: str) -> Path:
        return inside(self.ws.root, "exports", check_id(episode_id))

    def file_path(self, episode_id: str, name: str) -> Path:
        p = inside(self.dir_for(episode_id), check_id(name))
        if p.suffix.lower() not in FILE_SUFFIXES or not p.is_file():
            raise FileNotFoundError(name)
        return p

    def status(self, episode_id: str) -> dict | None:
        with self._lock:
            j = self.jobs.get(episode_id)
            return dict(j) if j else None

    def start(self, ep: Episode, formats: list[str], mp3_kbps: int = 128, channels: int = 2,
              wait: bool = False) -> dict:
        formats = [f for f in FORMATS if f in formats]
        if not formats:
            raise ValueError("no export format selected")
        with ep.lock:
            enabled = ep.enabled
            ep.timeline_for(enabled)           # refuses an invalid state before anything starts
            version = ep.version_key(enabled)
            music_version = EpisodeMusic(self.ws, ep).export_key()
            title = ep.meta.get("title", ep.id)
            show = ep.meta.get("show", DEFAULT_SHOW)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        job = {"id": uuid.uuid4().hex[:12], "state": "running", "progress": 0.0, "stage": tr("准备"),
               "version": version, "music_version": music_version, "formats": formats, "basename": f"{ep.id}_{stamp}",
               "started": time.time(), "finished": None, "result": None, "error": None}
        with self._lock:
            if self._running:
                raise ExportBusy(tr("另一个导出正在进行"))
            self._running = ep.id
            self.jobs[ep.id] = job
        out_dir = self.dir_for(ep.id)

        def progress(f: float, stage: str) -> None:
            with self._lock:
                job["progress"] = round(min(max(f, 0.0), 1.0), 3)
                job["stage"] = stage

        def run() -> None:
            pool = None
            try:
                progress(0.0, tr("配乐与 ducking"))
                tl, media, lay = EpisodeMusic(self.ws, ep).mix(enabled, channels)
                pool = declip.pool_for(ep, media)     # clipped peaks restored before mastering
                res = export(timeline_source(pool, tl, channels), tl.sample_rate, channels, out_dir,
                             job["basename"], tuple(formats), MasterSettings(), tl.length,
                             mp3_kbps, {"title": title, "artist": show, "album": show},
                             progress)
                record = {"episode": ep.id, "title": title, "version": version, "music_version": music_version,
                          "applied_edits": sorted(enabled), "exported_at": datetime.now().isoformat(),
                          "channels": channels, "music": credits(lay), **res.to_dict()}
                atomic_write_json(out_dir / f"{job['basename']}.json", record)
                files = {k: Path(v).name for k, v in res.files.items()}
                with self._lock:
                    job.update(state="done", progress=1.0, stage=tr("完成"), finished=time.time(),
                               result={"files": files, "report": record["report"], "mp3": res.mp3,
                                       "errors": res.errors, "folder": str(out_dir)})
                for hook in self.on_done:
                    try:
                        hook(ep)
                    except Exception:   # an after-export extra never turns a finished export red
                        traceback.print_exc()
            except Exception as e:   # surfaced to the UI; full trace on the console
                traceback.print_exc()
                with self._lock:
                    job.update(state="error", finished=time.time(), error=str(e) or type(e).__name__)
            finally:
                if pool:
                    pool.close()
                with self._lock:
                    self._running = None

        if wait:
            run()
        else:
            threading.Thread(target=run, name=f"export-{ep.id}", daemon=True).start()
        return dict(job)

    def open_folder(self, episode_id: str) -> str:
        d = self.dir_for(episode_id)
        d.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(d))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(d)])
        else:
            subprocess.Popen(["xdg-open", str(d)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(d)
