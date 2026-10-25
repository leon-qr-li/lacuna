"""Audio of episodes nobody has opened for a while lives in cloud storage, not on the server's disk
(decision 2026-10-25-audio-cold-storage, Leon 2026-10-25).

* **Moving out (`freeze`).** An hourly sweep (routes/cold.py) looks at every show's episodes. One not used
  (opened, edited, exported) for ``COLD_AFTER_S`` (14 days), with no import or export running and not open
  in memory, has its audio files uploaded to the R2 bucket (lacuna_app/r2.py), each checked there by size and
  SHA-256, then written down in ``<episode>/audio_store.json``; only then are the local copies deleted.
  Audio files are the raw tracks (``imported_tracks/``, ``recordings/``), the WAVs an import made or a person
  uploaded again (``imports/<id>/media/``, ``episodes/<id>/media|raw/``) and the exports (``exports/<id>/*.wav|mp3``).
  Files anywhere else (the shared sample show, the music library) never move. Everything else (transcript, edits,
  show notes, the clipping-repair cache) stays, so the episode list, search and learning never need the audio.
  An object's key is its SHA-256 (``audio/<sha256>``): the same file is stored once, and a file moved out
  again after a restore is not uploaded again.
* **Coming back (`thaw`).** Opening a cold episode (``AppContext.get``) starts a download in the background and
  answers 423 「正在取回音频」 with the progress; the page polls until it is done (10-30 s for an episode).
  Each file lands through a temporary name and only when its SHA-256 matches.
* **What R2 keeps.** A restored episode keeps its copies in R2 (``audio_store.json`` still lists them), so the
  next move out costs no upload. ``gc`` deletes objects no show references any more (a show emptied from the
  回收区, an episode deleted for good) once they are a week old.

The staging site reads from the same bucket but never moves anything out (``freezing`` off) and never deletes.
"""
from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path
from typing import Callable, Iterable

from . import declip
from .r2 import Bucket, R2Error, file_sha256
from .store import META_FILE, STATE_FILE, Workspace, atomic_write_json, read_json

STORE_FILE = "audio_store.json"
USED_FILE = "used.json"
COLD_AFTER_S = 14 * 86400
TOUCH_EVERY_S = 3600
GC_AGE_S = 7 * 86400
PREFIX = "audio/"
AUDIO_DIRS = ("imported_tracks", "recordings", "imports", "episodes", "exports")
EPISODE_AUDIO = ("media", "raw")         # the folders under imports/<id>/ and episodes/<id>/ that hold audio
EXPORT_SUFFIXES = (".wav", ".mp3")


# ------------------------------------------------------------------ what an episode's audio is
def _rel(root: Path, p: str | Path) -> str | None:
    """`p` relative to the show folder, when it is one of the audio places there; else None."""
    try:
        rel = Path(p).resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    parts = rel.parts
    if len(parts) < 2 or parts[0] not in AUDIO_DIRS:
        return None
    if parts[0] in ("imports", "episodes") and (len(parts) < 4 or parts[2] not in EPISODE_AUDIO):
        return None
    return rel.as_posix()


def referenced(ws: Workspace, episode_id: str) -> list[str]:
    """Every audio file the episode refers to, relative to the show folder (local or not)."""
    d = ws.episode_dir(episode_id)
    out: list[str] = []
    try:
        st = read_json(d / STATE_FILE)
        paths = [m.get("path") for m in st["project"]["media"]]
    except (OSError, ValueError, KeyError, TypeError):
        paths = []
    try:
        paths += list((read_json(d / META_FILE).get("raw_tracks") or {}).values())
    except (OSError, ValueError, AttributeError):
        pass
    exports = ws.root / "exports" / episode_id
    if exports.is_dir():
        paths += [p for p in exports.iterdir() if p.is_file() and p.suffix.lower() in EXPORT_SUFFIXES]
    for p in paths:
        r = _rel(ws.root, p) if p else None
        if r and r not in out:
            out.append(r)
    return out


def store_of(ep_dir: Path) -> dict:
    try:
        s = read_json(Path(ep_dir) / STORE_FILE)
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def is_cold(ep_dir: Path) -> bool:
    return bool(store_of(ep_dir).get("cold"))


def cold_paths(ep_dir: Path) -> set[str]:
    """Absolute paths of the episode's files that are in cloud storage now (Episode.missing_sources counts
    them as present: they come back when the episode is opened)."""
    s = store_of(ep_dir)
    if not s.get("cold"):
        return set()
    root = Path(ep_dir).resolve().parent.parent
    return {str((root / f["rel"]).resolve()) for f in s.get("files") or []}


def last_used(ep_dir: Path) -> float:
    """When the episode was last opened / edited / exported (its state file changes with every edit)."""
    ep_dir = Path(ep_dir)
    times = []
    for f in (USED_FILE, STATE_FILE):
        try:
            times.append((ep_dir / f).stat().st_mtime)
        except OSError:
            pass
    try:
        times.append(float(read_json(ep_dir / USED_FILE).get("at") or 0))
    except (OSError, ValueError, AttributeError):
        pass
    return max(times, default=0.0)


def touch(ep_dir: Path, now: float | None = None) -> None:
    """The episode is being used (at most one write an hour)."""
    now = time.time() if now is None else now
    p = Path(ep_dir) / USED_FILE
    try:
        if now - float(read_json(p).get("at") or 0) < TOUCH_EVERY_S:
            return
    except (OSError, ValueError, AttributeError):
        pass
    try:
        atomic_write_json(p, {"at": now})
    except OSError:
        pass


class Restoring(Exception):
    """The episode's audio is on its way back; `progress` 0..1."""

    def __init__(self, progress: float, error: str | None = None):
        super().__init__(error or "restoring")
        self.progress, self.error = progress, error


# ------------------------------------------------------------------ the store
class ColdStore:
    def __init__(self, bucket: Bucket | None, clock: Callable[[], float] = time.time, after_s: float = COLD_AFTER_S,
                 freezing: bool = True):
        self.bucket = bucket
        self.clock = clock
        self.after_s = after_s
        self.freezing = freezing and bucket is not None
        self._lock = threading.Lock()
        self._guards: dict[str, threading.Lock] = {}
        self._thaws: dict[str, dict] = {}       # episode folder -> {"done", "total", "error", "thread"}
        self._moving: set[str] = set()

    @property
    def on(self) -> bool:
        return self.bucket is not None

    def guard(self, ep_dir: Path) -> threading.Lock:
        k = str(Path(ep_dir).resolve())
        with self._lock:
            return self._guards.setdefault(k, threading.Lock())

    def active(self) -> int:
        """Episodes moving out or coming back right now (a restart would cut them off)."""
        with self._lock:
            return len(self._moving) + sum(1 for t in self._thaws.values() if t.get("error") is None)

    # ---------------------------------------------------------------- opening an episode
    def opening(self, ws: Workspace, episode_id: str) -> None:
        """Called before an episode is opened for work: notes the use, or raises Restoring while its audio comes
        back (the first call starts the download)."""
        d = ws.episode_dir(episode_id)
        with self.guard(d):
            if is_cold(d):
                self._thaw_async(ws, episode_id, d)
            else:
                touch(d, self.clock())
                return
        with self._lock:
            t = dict(self._thaws.get(str(d.resolve())) or {})
        if not t:          # finished between the two looks
            return self.opening(ws, episode_id)
        raise Restoring(t["done"] / t["total"] if t.get("total") else 0.0, t.get("error"))

    def _thaw_async(self, ws: Workspace, episode_id: str, d: Path) -> None:
        k = str(d.resolve())
        with self._lock:
            t = self._thaws.get(k)
            if t and (t.get("error") is None or self.clock() - t.get("at", 0) < 30):
                return            # running, or failed a moment ago (asked again soon: try again then)
            files = store_of(d).get("files") or []
            t = self._thaws[k] = {"done": 0, "total": sum(int(f.get("size") or 0) for f in files) or 1,
                                  "error": None, "at": self.clock()}

        def run():
            try:
                self.thaw(ws, episode_id, lambda n: t.__setitem__("done", t["done"] + n))
                with self._lock:
                    self._thaws.pop(k, None)
            except Exception as e:       # noqa: BLE001 - shown on the page; tried again on the next open
                traceback.print_exc()
                with self._lock:
                    t["error"], t["at"] = str(e) or type(e).__name__, self.clock()

        if self.bucket is None:
            t["error"] = "no audio store"
            return
        threading.Thread(target=run, daemon=True, name=f"thaw-{episode_id}").start()

    def thaw(self, ws: Workspace, episode_id: str, progress: Callable[[int], None] | None = None) -> None:
        """Bring the episode's audio back (blocking)."""
        d = ws.episode_dir(episode_id)
        s = store_of(d)
        if not s.get("cold"):
            return
        if self.bucket is None:
            raise R2Error("no audio store")
        for f in s.get("files") or []:
            dest = ws.root / f["rel"]
            if dest.is_file() and dest.stat().st_size == f["size"]:
                if progress:
                    progress(f["size"])
                continue
            self.bucket.get_file(f["key"], dest, f["sha256"], f["size"], progress)
        with self.guard(d):
            atomic_write_json(d / STORE_FILE, s | {"cold": False, "restored_at": self.clock()})
            touch(d, self.clock())

    # ---------------------------------------------------------------- moving out
    def freeze(self, ws: Workspace, episode_id: str, keep: Iterable[str] = (),
               in_use: Callable[[], bool] = lambda: False) -> int:
        """Move one episode's audio to cloud storage; returns the bytes freed (0: not moved). `keep`: files (relative
        to the show folder) another episode still plays from this disk; `in_use()`: the episode was opened or a job
        started meanwhile (checked again just before anything is deleted)."""
        if not self.freezing:
            return 0
        d = ws.episode_dir(episode_id)
        if is_cold(d) or self.clock() - last_used(d) < self.after_s or in_use():
            return 0
        if not self._repairs_cached(d):
            return 0      # opening it needs the audio once more (clipping repair); moved after that
        keep = set(keep)
        rels = [r for r in referenced(ws, episode_id) if r not in keep and (ws.root / r).is_file()]
        if not rels:
            return 0
        k = str(d.resolve())
        with self._lock:
            if k in self._moving:
                return 0
            self._moving.add(k)
        try:
            prev = {f["rel"]: f for f in store_of(d).get("files") or []}
            files = []
            for rel in rels:
                p = ws.root / rel
                size = p.stat().st_size
                old = prev.get(rel)
                sha = old["sha256"] if old and old.get("size") == size and _same_since(p, old) else file_sha256(p)
                key = PREFIX + sha
                if not self.bucket.exists(key, size, sha):
                    self.bucket.put_file(key, p, sha)
                    if not self.bucket.exists(key, size, sha):
                        raise R2Error(f"{rel}: not found in the audio store after the upload")
                files.append({"rel": rel, "size": size, "sha256": sha, "key": key, "mtime": p.stat().st_mtime})
            freed = 0
            with self.guard(d):
                if self.clock() - last_used(d) < self.after_s or in_use():
                    return 0          # opened while it was uploading: it stays (the copies in R2 are reused later)
                atomic_write_json(d / STORE_FILE, {"cold": True, "moved_at": self.clock(), "files": files})
                for f in files:
                    p = ws.root / f["rel"]
                    try:
                        size = p.stat().st_size
                        p.unlink()
                        freed += size
                    except OSError:
                        pass
            return freed
        finally:
            with self._lock:
                self._moving.discard(k)

    @staticmethod
    def _repairs_cached(d: Path) -> bool:
        try:
            st = read_json(d / STATE_FILE)
            voice = {c["media_id"] for t in st["project"]["base"]["tracks"] for c in t["clips"]}
        except (OSError, ValueError, KeyError, TypeError):
            return False
        return all(declip._path(d, mid).is_file() for mid in voice)

    # ---------------------------------------------------------------- the sweep
    def sweep(self, shows: Iterable[tuple[Workspace, Callable[[str], bool]]]) -> dict:
        """Move out every episode that may go. `shows`: (workspace, busy(episode id)) for every show."""
        moved, freed, failed = 0, 0, 0
        if not self.freezing:
            return {"moved": 0, "freed": 0, "failed": 0}
        for ws, busy in shows:
            try:
                ids = ws.episode_ids()
            except OSError:
                continue
            refs = {eid: referenced(ws, eid) for eid in ids}
            for eid in ids:
                d = ws.episode_dir(eid)
                if is_cold(d):
                    continue
                keep = {r for other, rs in refs.items() if other != eid and not is_cold(ws.episode_dir(other))
                        for r in rs}
                try:
                    n = self.freeze(ws, eid, keep, lambda e=eid: busy(e))
                except Exception:        # noqa: BLE001 - this one stays on the disk; tried again next sweep
                    traceback.print_exc()
                    failed += 1
                    continue
                if n:
                    moved += 1
                    freed += n
        return {"moved": moved, "freed": freed, "failed": failed}

    def gc(self, roots: Iterable[Path]) -> int:
        """Delete objects no audio_store.json under `roots` lists (and older than GC_AGE_S); returns how many."""
        if not self.freezing:
            return 0
        wanted: set[str] = set()
        for root in roots:
            root = Path(root)
            if not root.is_dir():
                continue
            for p in root.rglob(STORE_FILE):
                for f in store_of(p.parent).get("files") or []:
                    wanted.add(f.get("key"))
        gone = 0
        for o in self.bucket.keys(PREFIX):
            if o["key"] not in wanted and self.clock() - o["modified"] > GC_AGE_S:
                self.bucket.delete(o["key"])
                gone += 1
        return gone

    def stored_bytes(self, roots: Iterable[Path]) -> int:
        """Bytes of audio in cloud storage now (cold episodes), from the episodes' own records."""
        seen: dict[str, int] = {}
        for root in roots:
            root = Path(root)
            if not root.is_dir():
                continue
            for p in root.rglob(STORE_FILE):
                s = store_of(p.parent)
                for f in s.get("files") or []:
                    seen[f.get("key")] = int(f.get("size") or 0)
        return sum(seen.values())


def _same_since(p: Path, rec: dict) -> bool:
    try:
        return abs(p.stat().st_mtime - float(rec.get("mtime") or -1)) < 1e-3
    except OSError:
        return False
