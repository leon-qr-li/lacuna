"""Stress test of the cloud audio store (lacuna_app/cold.py + lacuna_app/r2.py, decision 2026-10-25-audio-cold-storage).

Runs the real ColdStore and the real R2 client against a local S3-compatible server that injects faults: 503s,
connections dropped in the middle of a body, flipped bytes on download, a "disk full" while restoring. Checks after
every round that no audio was lost or replaced by wrong bytes:

  1. hashing speed (every freeze / restore hashes the whole file; the server has 4 vCPU like this machine)
  2. many episodes moved out at once while the store misbehaves; a second sweep finishes the rest without uploading
     anything twice
  3. half of them opened while they were being uploaded: those keep their audio
  4. every cold episode opened at the same time (people coming back after the beta's quiet weeks), with faults
  5. the disk fills up during a restore: nothing half-written stays, the episode stays cold and comes back later
  6. large tracks (multipart upload) with faults
  7. garbage collection after episodes are deleted for good

    python scripts/stress_cold_storage.py [--episodes 24] [--tracks 3] [--mb 24] [--big-mb 48] [--out report.json]

Nothing touches the real bucket; the numbers for upload / download speed are this machine's loopback, not the
server's link to R2 (see docs/status/batch-6.md for how that one is measured).
"""
from __future__ import annotations

import argparse
import builtins
import errno
import hashlib
import json
import os
import random
import shutil
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lacuna_app import declip, r2  # noqa: E402
from lacuna_app.cold import COLD_AFTER_S, STORE_FILE, ColdStore, Restoring, is_cold, referenced  # noqa: E402
from lacuna_app.store import META_FILE, STATE_FILE, Workspace, atomic_write_json  # noqa: E402

DAY = 86400


# ------------------------------------------------------------------ a local S3 with faults
class Faults:
    def __init__(self):
        self.p503 = 0.0          # answer 503 before doing anything
        self.pdrop = 0.0         # close the connection halfway through a body (both directions)
        self.pflip = 0.0         # flip one byte of a download
        self.lock = threading.Lock()
        self.count = {"503": 0, "drop": 0, "flip": 0, "requests": 0, "put_bytes": 0, "get_bytes": 0, "puts": 0}

    def roll(self, p: float, what: str) -> bool:
        if p and random.random() < p:
            with self.lock:
                self.count[what] += 1
            return True
        return False

    def add(self, what: str, n: int = 1) -> None:
        with self.lock:
            self.count[what] += n


class S3:
    """Objects as files under `root`; metadata (sha256 header, time) in a dict."""

    def __init__(self, root: Path, faults: Faults):
        self.root, self.faults = root, faults
        self.meta: dict[str, dict] = {}
        self.uploads: dict[str, dict] = {}
        self.lock = threading.Lock()

    def path(self, key: str) -> Path:
        return self.root / hashlib.sha1(key.encode()).hexdigest()


def handler(s3: S3):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _key(self):
            u = urllib.parse.urlsplit(self.path)
            parts = urllib.parse.unquote(u.path).lstrip("/").split("/", 1)
            return (parts[1] if len(parts) > 1 else ""), dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))

        def _send(self, code, body=b"", headers=None):
            self.send_response(code)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _fault(self) -> bool:
            s3.faults.add("requests")
            if s3.faults.roll(s3.faults.p503, "503"):
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)
                self._send(503, b"<Error><Code>ServiceUnavailable</Code></Error>")
                return True
            return False

        def _read_body(self):
            """The request body, checked against x-amz-content-sha256 like R2 does; None when the client's
            connection was cut (simulated)."""
            n = int(self.headers.get("Content-Length") or 0)
            if s3.faults.roll(s3.faults.pdrop, "drop"):
                self.rfile.read(n // 2)
                self.close_connection = True
                self.connection.shutdown(2)
                return None
            data = self.rfile.read(n)
            want = self.headers.get("x-amz-content-sha256")
            if want and want != "UNSIGNED-PAYLOAD" and hashlib.sha256(data).hexdigest() != want:
                self._send(400, b"<Error><Code>BadDigest</Code></Error>")
                return None
            return data

        def do_HEAD(self):
            if self._fault():
                return
            key, _ = self._key()
            m = s3.meta.get(key)
            if not m:
                return self._send(404)
            self.send_response(200)
            self.send_header("Content-Length", str(m["size"]))
            self.send_header("x-amz-meta-sha256", m["sha256"])
            self.end_headers()

        def do_PUT(self):
            if self._fault():
                return
            key, q = self._key()
            data = self._read_body()
            if data is None:
                return
            s3.faults.add("put_bytes", len(data))
            s3.faults.add("puts")
            if "uploadId" in q:
                up = s3.uploads.get(q["uploadId"])
                if up is None:
                    return self._send(404)
                up["parts"][int(q["partNumber"])] = data
                return self._send(200, headers={"ETag": f'"{hashlib.md5(data).hexdigest()}"'})
            p = s3.path(key)
            tmp = p.with_suffix(".tmp" + str(threading.get_ident()))
            tmp.write_bytes(data)
            os.replace(tmp, p)
            with s3.lock:
                s3.meta[key] = {"size": len(data), "sha256": self.headers.get("x-amz-meta-sha256"), "at": time.time()}
            self._send(200, headers={"ETag": '"x"'})

        def do_POST(self):
            if self._fault():
                return
            key, q = self._key()
            if "uploads" in q:
                uid = os.urandom(8).hex()
                s3.uploads[uid] = {"key": key, "parts": {}, "sha256": self.headers.get("x-amz-meta-sha256")}
                return self._send(200, f"<InitiateMultipartUploadResult><UploadId>{uid}</UploadId>"
                                       f"</InitiateMultipartUploadResult>".encode())
            data = self._read_body()
            if data is None:
                return
            up = s3.uploads.pop(q.get("uploadId"), None)
            if up is None:
                return self._send(404)
            blob = b"".join(up["parts"][n] for n in sorted(up["parts"]))
            s3.path(key).write_bytes(blob)
            with s3.lock:
                s3.meta[key] = {"size": len(blob), "sha256": up["sha256"], "at": time.time()}
            self._send(200, b"<CompleteMultipartUploadResult/>")

        def do_DELETE(self):
            if self._fault():
                return
            key, q = self._key()
            if "uploadId" in q:
                s3.uploads.pop(q["uploadId"], None)
                return self._send(204)
            with s3.lock:
                s3.meta.pop(key, None)
            s3.path(key).unlink(missing_ok=True)
            self._send(204)

        def do_GET(self):
            if self._fault():
                return
            key, q = self._key()
            if q.get("list-type") == "2":
                pre = q.get("prefix", "")
                items = "".join(
                    f"<Contents><Key>{k}</Key><Size>{m['size']}</Size><LastModified>"
                    f"{time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(m['at']))}</LastModified></Contents>"
                    for k, m in sorted(s3.meta.items()) if k.startswith(pre))
                return self._send(200, f"<ListBucketResult><IsTruncated>false</IsTruncated>{items}</ListBucketResult>".encode())
            m = s3.meta.get(key)
            if not m:
                return self._send(404, b"<Error><Code>NoSuchKey</Code></Error>")
            size = m["size"]
            drop_at = random.randint(1, max(1, size - 1)) if s3.faults.roll(s3.faults.pdrop, "drop") else None
            flip_at = random.randint(0, size - 1) if size and s3.faults.roll(s3.faults.pflip, "flip") else None
            self.send_response(200)
            self.send_header("Content-Length", str(size))
            self.end_headers()
            sent = 0
            with open(s3.path(key), "rb") as f:
                while True:
                    b = f.read(1 << 20)
                    if not b:
                        break
                    if flip_at is not None and sent <= flip_at < sent + len(b):
                        i = flip_at - sent
                        b = b[:i] + bytes([b[i] ^ 0xFF]) + b[i + 1:]
                    if drop_at is not None and sent + len(b) > drop_at:
                        self.wfile.write(b[: drop_at - sent])
                        self.wfile.flush()
                        self.close_connection = True
                        self.connection.shutdown(2)
                        return
                    self.wfile.write(b)
                    sent += len(b)
            s3.faults.add("get_bytes", sent)

    return H


class LocalBucket(r2.Bucket):
    """The real client, sent to the local server over plain HTTP (same paths, same signing)."""

    RETRY_WAITS = (0.05, 0.1, 0.2)

    def __init__(self, port: int):
        super().__init__("https://r2.local/lacuna-audio", "id", "secret", sleep=time.sleep)
        self.port = port

    def send(self, method, url, headers, body=None, stream=False):
        return super().send(method, url.replace("https://r2.local", f"http://127.0.0.1:{self.port}"), headers, body, stream)


# ------------------------------------------------------------------ a show with many episodes
def make_show(root: Path, episodes: int, tracks: int, mb: int) -> Workspace:
    ws = Workspace(root)
    for i in range(episodes):
        eid = f"EP{i:03d}"
        d = ws.episode_dir(eid)
        raw = d / "raw"
        raw.mkdir(parents=True)
        media = []
        for t in range(tracks):
            p = raw / f"track{t}.wav"
            with open(p, "wb") as f:
                for _ in range(mb):
                    f.write(os.urandom(1 << 20))
            media.append({"id": f"m{t}", "path": str(p.resolve())})
        atomic_write_json(d / STATE_FILE, {"project": {"media": media, "base": {
            "tracks": [{"clips": [{"media_id": m["id"]}]} for m in media]}}})
        atomic_write_json(d / META_FILE, {"id": eid})
        for m in media:                     # the clipping-repair cache, as after the first open
            c = declip._path(d, m["id"])
            c.parent.mkdir(parents=True, exist_ok=True)
            c.write_bytes(b"cache")
        old = time.time() - COLD_AFTER_S - DAY
        os.utime(d / STATE_FILE, (old, old))
    return ws


def age(ws: Workspace, eids, now: float) -> None:
    """Make the episodes look unused for 15 days (as of `now`)."""
    old = now - COLD_AFTER_S - DAY
    for e in eids:
        d = ws.episode_dir(e)
        atomic_write_json(d / "used.json", {"at": old})
        for f in ("used.json", STATE_FILE):
            os.utime(d / f, (old, old))


def digests(ws: Workspace) -> dict[str, str]:
    out = {}
    for eid in ws.episode_ids():
        for rel in referenced(ws, eid):
            out[rel] = r2.file_sha256(ws.root / rel)
    return out


def check_local(ws: Workspace, want: dict[str, str], eids) -> list[str]:
    """Problems: an episode that isn't cold but lacks a file, or a file with other bytes."""
    bad = []
    for eid in eids:
        d = ws.episode_dir(eid)
        for rel in referenced(ws, eid):
            p = ws.root / rel
            if is_cold(d):
                continue
            if not p.is_file():
                bad.append(f"{rel}: missing on a warm episode")
            elif r2.file_sha256(p) != want[rel]:
                bad.append(f"{rel}: wrong bytes")
        bad += [f"{x}: leftover" for x in d.rglob("*.restoring")]
    return bad


def check_cold(ws: Workspace, s3: S3, eids) -> list[str]:
    bad = []
    for eid in eids:
        d = ws.episode_dir(eid)
        if not is_cold(d):
            continue
        for f in json.loads((d / STORE_FILE).read_text())["files"]:
            m = s3.meta.get(f["key"])
            if not m or m["size"] != f["size"] or r2.file_sha256(s3.path(f["key"])) != f["sha256"]:
                bad.append(f"{f['rel']}: not intact in the store")
            if (ws.root / f["rel"]).exists():
                bad.append(f"{f['rel']}: cold but still on disk")
    return bad


# ------------------------------------------------------------------ disk full during a restore
class DiskBudget:
    """While on, writes through files opened for ".restoring" fail with ENOSPC once `left` bytes are used."""

    def __init__(self):
        self.left = None
        self.real_open = builtins.open
        self.lock = threading.Lock()

    def open(self, file, mode="r", *a, **k):
        f = self.real_open(file, mode, *a, **k)
        if self.left is None or "w" not in mode or not str(file).endswith(".restoring"):
            return f
        budget = self

        class Limited:
            def __init__(self, inner):
                self.inner = inner

            def write(self, b):
                with budget.lock:
                    if budget.left is not None and budget.left < len(b):
                        raise OSError(errno.ENOSPC, "No space left on device")
                    if budget.left is not None:
                        budget.left -= len(b)
                return self.inner.write(b)

            def __getattr__(self, n):
                return getattr(self.inner, n)

            def __enter__(self):
                return self

            def __exit__(self, *e):
                self.inner.close()

        return Limited(f)


# ------------------------------------------------------------------ the rounds
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=24)
    ap.add_argument("--tracks", type=int, default=3)
    ap.add_argument("--mb", type=int, default=24, help="MB per track")
    ap.add_argument("--big-mb", type=int, default=48, help="MB of the multipart track")
    ap.add_argument("--hash-mb", type=int, default=1024)
    ap.add_argument("--real-parts", action="store_true",
                    help="keep the client's real sizes (one request up to 1 GB, 256 MB parts): use --big-mb 1200+")
    ap.add_argument("--out")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--chaos", type=float, default=1.0, help="multiply every fault rate (4 = a very bad day)")
    args = ap.parse_args()
    random.seed(args.seed)
    tmp = Path(tempfile.mkdtemp(prefix="lacuna-stress-"))
    report: dict = {"setup": vars(args) | {"cpus": os.cpu_count()}, "rounds": {}}
    problems: list[str] = []
    try:
        (tmp / "objects").mkdir()
        faults = Faults()
        s3 = S3(tmp / "objects", faults)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(s3))
        srv.handle_error = lambda *a: None             # the dropped connections are on purpose
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        bucket = LocalBucket(srv.server_address[1])

        # 1. hashing speed
        big = tmp / "hash.bin"
        with open(big, "wb") as f:
            for _ in range(args.hash_mb):
                f.write(os.urandom(1 << 20))
        t0 = time.time()
        r2.file_sha256(big)
        dt = time.time() - t0
        report["rounds"]["hash"] = {"mb": args.hash_mb, "s": round(dt, 2), "mb_per_s": round(args.hash_mb / dt)}
        big.unlink()

        ws = make_show(tmp / "show", args.episodes, args.tracks, args.mb)
        eids = ws.episode_ids()
        want = digests(ws)
        total_mb = args.episodes * args.tracks * args.mb
        clock_shift = [0.0]
        store = ColdStore(bucket, clock=lambda: time.time() + clock_shift[0])

        # 2. moving out with faults, then a second sweep
        faults.p503, faults.pdrop = 0.05 * args.chaos, 0.03 * args.chaos
        t0 = time.time()
        first = store.sweep([(ws, lambda _e: False)])
        dt1 = time.time() - t0
        puts_after_first = faults.count["puts"]
        uploaded_first = faults.count["put_bytes"]
        faults.p503 = faults.pdrop = 0.0
        second = store.sweep([(ws, lambda _e: False)])
        problems += check_local(ws, want, eids) + check_cold(ws, s3, eids)
        cold_now = sum(is_cold(ws.episode_dir(e)) for e in eids)
        report["rounds"]["freeze"] = {
            "episodes": len(eids), "audio_mb": total_mb, "first_sweep": first, "first_s": round(dt1, 1),
            "upload_mb_per_s": round(uploaded_first / 2**20 / dt1, 1), "second_sweep": second,
            "cold_after": cold_now, "faults": dict(faults.count),
            "extra_upload_mb": round((faults.count["put_bytes"] - total_mb * 2**20) / 2**20, 1),
            "puts_first": puts_after_first}
        if cold_now != len(eids):
            problems.append(f"only {cold_now}/{len(eids)} episodes moved out after two sweeps")

        # 3. thaw everything, then move out again while half of them get opened mid-upload
        for e in eids:
            store.thaw(ws, e)
        problems += check_local(ws, want, eids)
        age(ws, eids, time.time() + clock_shift[0])     # they look old again
        for k in s3.meta:                               # force fresh uploads (a new bucket)
            s3.path(k).unlink(missing_ok=True)
        s3.meta.clear()
        opened = set(eids[::2])
        looks: dict[str, int] = {}

        def busy(e):
            looks[e] = looks.get(e, 0) + 1
            return e in opened and looks[e] > 1         # free when the sweep starts, opened before it deletes
        race = store.sweep([(ws, busy)])
        problems += check_local(ws, want, eids) + check_cold(ws, s3, eids)
        kept = [e for e in opened if is_cold(ws.episode_dir(e))]
        if kept:
            problems.append(f"{len(kept)} episodes opened during the upload were moved out anyway")
        report["rounds"]["opened_while_uploading"] = {"sweep": race, "opened": len(opened),
                                                     "wrongly_moved": len(kept)}
        store.sweep([(ws, lambda _e: False)])

        # 4. everyone opens at once, with faults
        faults.p503, faults.pdrop, faults.pflip = (0.05 * args.chaos, 0.05 * args.chaos, 0.03 * args.chaos)
        for k in ("503", "drop", "flip", "get_bytes"):
            faults.count[k] = 0
        t0 = time.time()
        states: dict[str, str] = {}
        polls = [0]
        first_error: dict[str, str] = {}

        def visitor(e):
            while True:
                try:
                    store.opening(ws, e)
                    states[e] = "open"
                    return
                except Restoring as r:
                    polls[0] += 1
                    if r.error:
                        first_error.setdefault(e, r.error)
                        clock_shift[0] += 31       # the page asks again; after 30 s a failed restore restarts
                    if time.time() - t0 > 600:
                        states[e] = f"gave up: {r.error}"
                        return
                    time.sleep(0.05)
        th = [threading.Thread(target=visitor, args=(e,)) for e in eids]
        for t in th:
            t.start()
        for t in th:
            t.join()
        dt = time.time() - t0
        problems += check_local(ws, want, eids)
        not_open = {e: s for e, s in states.items() if s != "open"}
        if not_open:
            problems.append(f"{len(not_open)} episodes never came back")
        report["rounds"]["everyone_opens"] = {
            "episodes": len(eids), "audio_mb": total_mb, "s": round(dt, 1),
            "download_mb_per_s": round(faults.count["get_bytes"] / 2**20 / dt, 1), "faults": {
                k: faults.count[k] for k in ("503", "drop", "flip")},
            "episodes_that_failed_once_and_retried": len(first_error),
            "errors_seen": sorted({v.split(":")[0][:80] for v in first_error.values()}),
            "all_back": not not_open}
        faults.p503 = faults.pdrop = faults.pflip = 0.0

        # 5. disk full during a restore
        age(ws, eids, time.time() + clock_shift[0])
        store.sweep([(ws, lambda _e: False)])
        victim = eids[0]
        budget = DiskBudget()
        budget.left = args.mb * 2**20 // 2                  # half a track fits
        r2.open = budget.open                              # the client's open() for the .restoring file
        err = None
        try:
            store.thaw(ws, victim)
        except Exception as e:      # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        finally:
            del r2.open
        d = ws.episode_dir(victim)
        leftovers = list(d.rglob("*.restoring"))
        still_cold = is_cold(d)
        store.thaw(ws, victim)                              # space freed: it comes back
        problems += check_local(ws, want, [victim])
        report["rounds"]["disk_full"] = {"error": err, "stayed_cold": still_cold, "leftover_partial_files": len(leftovers),
                                         "came_back_after": not is_cold(d)}
        if not err or not still_cold or leftovers:
            problems.append("disk full during a restore was not handled cleanly")

        # 6. a big track: multipart upload with faults
        if not args.real_parts:
            r2.ONE_SHOT, r2.PART = 8 << 20, 5 << 20
        bigws = make_show(tmp / "bigshow", 1, 1, args.big_mb)
        bwant = digests(bigws)
        faults.p503, faults.pdrop = 0.10 * args.chaos, 0.10 * args.chaos
        t0 = time.time()
        bres, berr = None, None
        try:
            bres = store.sweep([(bigws, lambda _e: False)])
            faults.p503 = faults.pdrop = 0.0
            if bres["moved"] == 0:
                bres = store.sweep([(bigws, lambda _e: False)])
            faults.p503, faults.pdrop, faults.pflip = 0.10 * args.chaos, 0.10 * args.chaos, 0.05 * args.chaos
            for _ in range(5):
                try:
                    store.thaw(bigws, "EP000")
                    break
                except Exception as e:      # noqa: BLE001
                    berr = f"{type(e).__name__}: {e}"
        finally:
            faults.p503 = faults.pdrop = faults.pflip = 0.0
        problems += check_local(bigws, bwant, ["EP000"])
        report["rounds"]["multipart"] = {"mb": args.big_mb, "parts": -(-(args.big_mb << 20) // r2.PART), "sweep": bres,
                                         "came_back": not is_cold(bigws.episode_dir("EP000")), "last_error": berr,
                                         "open_uploads_left": len(s3.uploads), "s": round(time.time() - t0, 1)}

        # 7. garbage collection after deleting half the episodes for good
        gone = eids[: len(eids) // 2]
        for e in gone:
            shutil.rmtree(ws.episode_dir(e))
        before = len(s3.meta)
        n0 = store.gc([ws.root, bigws.root])                # too young: kept a week
        clock_shift[0] += 8 * DAY
        n1 = store.gc([ws.root, bigws.root])
        left = [e for e in eids if e not in gone]
        problems += check_cold(ws, s3, left)
        for e in left:
            store.thaw(ws, e)
        problems += check_local(ws, want, left)
        report["rounds"]["gc"] = {"objects_before": before, "deleted_while_young": n0, "deleted_after_a_week": n1,
                                  "objects_after": len(s3.meta), "kept_episodes_restore_ok": True}
        srv.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    report["problems"] = problems
    out = json.dumps(report, indent=2, ensure_ascii=False)
    print(out)
    if args.out:
        Path(args.out).write_text(out)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
