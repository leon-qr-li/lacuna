"""Server ↔ cloud storage speed test (batch 7, S1, decision 2026-10-25-copy-sweep).

The owner presses 「测速」 in the admin area (系统健康 → 存储与保留): the server writes a test file of random bytes
(200 MB) next to the audio, sends it to the R2 bucket the old episodes' audio goes to (lacuna_app/cold.py), fetches it
back, and deletes both the object and the local files whatever happens. The seconds each way are what moving an
episode out and bringing it back costs. One test at a time; the result stays until the next one (in memory)."""
from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path
from typing import Callable

from .i18n import tr
from .r2 import Bucket, file_sha256

SIZE = 200 * 1024 * 1024
CHUNK = 4 * 1024 * 1024
PREFIX = "_speedtest/"


class SpeedTest:
    def __init__(self, bucket: Callable[[], Bucket | None], work_dir: Path, size: int = SIZE,
                 clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time):
        self.bucket, self.dir, self.size, self.clock, self.wall = bucket, Path(work_dir), size, clock, wall
        self._lock = threading.Lock()
        self.last: dict = {"state": "idle"}

    def view(self) -> dict:
        with self._lock:
            return dict(self.last)

    def start(self, background: bool = True) -> dict:
        """Start a test; the caller polls ``view()``. Refuses while one runs, without a bucket, or without room."""
        b = self.bucket()
        if b is None:
            raise ValueError(tr("服务器还没有云存储的密钥，测不了。"))
        if shutil.disk_usage(self.dir.parent if not self.dir.exists() else self.dir).free < 3 * self.size:
            raise ValueError(tr("服务器磁盘空间不够，先清一清再测。"))
        with self._lock:
            if self.last.get("state") == "running":
                raise ValueError(tr("已经在测了，等它测完。"))
            self.last = {"state": "running", "stage": "upload", "size": self.size, "started": self.wall()}
        if background:
            threading.Thread(target=self._run, args=(b,), daemon=True, name="speedtest").start()
        else:
            self._run(b)
        return self.view()

    def _set(self, **kw) -> None:
        with self._lock:
            self.last.update(kw)

    def _run(self, b: Bucket) -> None:
        src, back = self.dir / "speedtest.bin", self.dir / "speedtest.back"
        key = f"{PREFIX}{int(self.wall())}.bin"
        sent = False
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            for o in list(b.keys(PREFIX)):      # a leftover from a test that could not delete its object
                b.delete(o["key"])
            with open(src, "wb") as f:
                left = self.size
                while left > 0:
                    n = min(CHUNK, left)
                    f.write(os.urandom(n))
                    left -= n
            sha = file_sha256(src)
            t0 = self.clock()
            b.put_file(key, src, sha)
            sent = True
            up = self.clock() - t0
            self._set(stage="download", upload_s=round(up, 2))
            t0 = self.clock()
            b.get_file(key, back, sha, self.size)
            down = self.clock() - t0
            self._set(state="done", stage=None, download_s=round(down, 2), finished=self.wall(),
                      upload_mbps=round(self.size * 8 / 1e6 / max(up, 1e-6), 1),
                      download_mbps=round(self.size * 8 / 1e6 / max(down, 1e-6), 1))
        except Exception as e:      # noqa: BLE001 - the owner sees that it failed; the details stay in the log
            print(f"LACUNA: speed test failed: {e!r}", flush=True)
            self._set(state="error", stage=None, finished=self.wall(), error=tr("测速没完成，请稍后再试。"))
        finally:
            for p in (src, back, back.with_name(back.name + ".restoring")):
                p.unlink(missing_ok=True)
            if sent:
                try:
                    b.delete(key)
                except Exception as e:      # noqa: BLE001 - a small leftover; the next test tries again
                    print(f"LACUNA: speed test object left in the bucket: {e!r}", flush=True)
