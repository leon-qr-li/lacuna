"""A small S3 client for Cloudflare R2 (decision 2026-10-25-audio-cold-storage): put, get, head, delete and list
objects of one bucket, signed with AWS Signature V4. Only the standard library: the app needs five calls, not an
SDK. Large files go up in parts (R2 takes at most 5 GB in one request); every request carries the SHA-256 of
its body, so R2 refuses bytes that changed on the way.

``Bucket.from_env()`` reads ``LACUNA_AUDIO_STORE`` (``https://<account>.r2.cloudflarestorage.com/<bucket>``),
``LACUNA_AUDIO_KEY_ID`` and ``LACUNA_AUDIO_SECRET`` (deploy/provision.py writes them); without them there is no
cold storage and the audio simply stays on the server.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator
from xml.etree import ElementTree

REGION = "auto"
PART = 256 << 20                # bytes per part of a large upload
ONE_SHOT = 1 << 30              # files up to this go up in one request
BLOCK = 1 << 20
EMPTY = hashlib.sha256(b"").hexdigest()
_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


class R2Error(RuntimeError):
    pass


def _quote(s: str) -> str:
    return urllib.parse.quote(s, safe="-_.~/")


def file_sha256(path: Path, start: int = 0, length: int | None = None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        f.seek(start)
        left = length
        while left is None or left > 0:
            b = f.read(BLOCK if left is None else min(BLOCK, left))
            if not b:
                break
            h.update(b)
            if left is not None:
                left -= len(b)
    return h.hexdigest()


def sign(method: str, host: str, path: str, query: dict[str, str], headers: dict[str, str], payload_hash: str,
         key_id: str, secret: str, now: datetime, region: str = REGION, service: str = "s3") -> dict[str, str]:
    """`headers` plus x-amz-date, x-amz-content-sha256 and Authorization (AWS Signature V4)."""
    amz = now.strftime("%Y%m%dT%H%M%SZ")
    day = amz[:8]
    h = {k.lower(): str(v).strip() for k, v in headers.items()}
    h |= {"host": host, "x-amz-date": amz, "x-amz-content-sha256": payload_hash}
    names = sorted(h)
    canonical = "\n".join([
        method, _quote(path),
        "&".join(f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
                 for k, v in sorted(query.items())),
        "".join(f"{n}:{re.sub(r' +', ' ', h[n])}\n" for n in names),
        ";".join(names), payload_hash])
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    k = f"AWS4{secret}".encode()
    for part in (day, region, service, "aws4_request"):
        k = hmac.new(k, part.encode(), hashlib.sha256).digest()
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    out = {k2: v for k2, v in headers.items()}
    out |= {"x-amz-date": amz, "x-amz-content-sha256": payload_hash,
            "Authorization": f"AWS4-HMAC-SHA256 Credential={key_id}/{scope}, SignedHeaders={';'.join(names)}, Signature={sig}"}
    return out


class _Slice:
    """Part of a file as a body for urllib (read in blocks, never all in memory)."""

    def __init__(self, path: Path, start: int, length: int, progress: Callable[[int], None] | None = None):
        self.f = open(path, "rb")
        self.f.seek(start)
        self.left = length
        self.progress = progress

    def read(self, n: int = -1) -> bytes:
        if self.left <= 0:
            return b""
        n = self.left if n is None or n < 0 else min(n, self.left)
        b = self.f.read(n)
        self.left -= len(b)
        if self.progress and b:
            self.progress(len(b))
        return b

    def close(self) -> None:
        self.f.close()


class Bucket:
    """One R2 bucket. `send` does the HTTP (tests replace it): (method, url, headers, body) -> (status, headers, body
    bytes or a readable response for `stream`)."""

    RETRY_WAITS = (2, 5, 15)

    def __init__(self, endpoint: str, key_id: str, secret: str, sleep: Callable[[float], None] = time.sleep):
        u = urllib.parse.urlsplit(endpoint.rstrip("/"))
        if u.scheme != "https" or not u.netloc or not u.path.strip("/"):
            raise R2Error("the audio store address must be https://<host>/<bucket>")
        self.host, self.bucket = u.netloc, u.path.strip("/")
        self.key_id, self.secret, self.sleep = key_id, secret, sleep

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Bucket | None":
        env = os.environ if env is None else env
        url, kid, sec = env.get("LACUNA_AUDIO_STORE"), env.get("LACUNA_AUDIO_KEY_ID"), env.get("LACUNA_AUDIO_SECRET")
        return cls(url, kid, sec) if url and kid and sec else None

    # ---------------------------------------------------------------- HTTP
    def send(self, method: str, url: str, headers: dict, body=None, stream: bool = False):
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            r = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()
        if stream:
            return r.status, dict(r.headers), r
        with r:
            return r.status, dict(r.headers), r.read()

    def _call(self, method: str, key: str, query: dict | None = None, headers: dict | None = None,
              body=None, payload_hash: str = EMPTY, stream: bool = False, ok=(200,), body_again=None):
        """One signed request, tried again on a dropped connection / 5xx / 429 (`body_again()` gives a fresh body)."""
        query = query or {}
        path = f"/{self.bucket}/{key}" if key else f"/{self.bucket}"
        for wait in (*self.RETRY_WAITS, None):
            h = sign(method, self.host, path, query, dict(headers or {}), payload_hash, self.key_id, self.secret,
                     datetime.now(timezone.utc))
            url = f"https://{self.host}{_quote(path)}"
            if query:
                url += "?" + urllib.parse.urlencode(sorted(query.items()), quote_via=urllib.parse.quote)
            try:
                status, rh, out = self.send(method, url, h, body, stream)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                status, rh, out = 0, {}, str(e).encode()
            if status in ok:
                return status, {k.lower(): v for k, v in rh.items()}, out
            if wait is None or (status and status < 500 and status != 429):
                break
            self.sleep(wait)
            if body_again is not None:
                body = body_again()
        raise R2Error(f"{method} {key or '/'} -> {status or 'no answer'}")

    # ---------------------------------------------------------------- objects
    def head(self, key: str) -> dict | None:
        """{size, sha256} of an object, or None when there is none."""
        st, h, _ = self._call("HEAD", key, ok=(200, 404))
        if st != 200:
            return None
        return {"size": int(h.get("content-length") or 0), "sha256": h.get("x-amz-meta-sha256")}

    def exists(self, key: str, size: int, sha256: str) -> bool:
        h = self.head(key)
        return h is not None and h["size"] == size and h["sha256"] == sha256

    def put_file(self, key: str, path: Path, sha256: str, progress: Callable[[int], None] | None = None) -> None:
        size = Path(path).stat().st_size
        meta = {"x-amz-meta-sha256": sha256}
        if size <= ONE_SHOT:
            mk = lambda: _Slice(path, 0, size, progress)     # noqa: E731
            body = mk()
            try:
                self._call("PUT", key, headers=meta | {"Content-Length": str(size)}, body=body, payload_hash=sha256,
                           body_again=mk)
            finally:
                body.close()
            return
        _, _, out = self._call("POST", key, {"uploads": ""}, headers=meta)
        root = ElementTree.fromstring(out)
        upload = root.findtext(f"{_NS}UploadId") or root.findtext("UploadId")
        if not upload:
            raise R2Error(f"no upload id for {key}")
        parts = []
        try:
            for n, start in enumerate(range(0, size, PART), 1):
                length = min(PART, size - start)
                ph = file_sha256(path, start, length)
                mk = lambda s=start, ln=length: _Slice(path, s, ln, progress)   # noqa: E731
                body = mk()
                try:
                    _, h, _ = self._call("PUT", key, {"partNumber": str(n), "uploadId": upload},
                                         headers={"Content-Length": str(length)}, body=body, payload_hash=ph,
                                         body_again=mk)
                finally:
                    body.close()
                parts.append((n, h.get("etag", "")))
            xml = ("<CompleteMultipartUpload>" + "".join(
                f"<Part><PartNumber>{n}</PartNumber><ETag>{e}</ETag></Part>" for n, e in parts)
                + "</CompleteMultipartUpload>").encode()
            self._call("POST", key, {"uploadId": upload}, headers={"Content-Length": str(len(xml))}, body=xml,
                       payload_hash=hashlib.sha256(xml).hexdigest())
        except BaseException:
            try:
                self._call("DELETE", key, {"uploadId": upload}, ok=(200, 204, 404))
            except R2Error:
                pass
            raise

    def get_file(self, key: str, dest: Path, sha256: str, size: int,
                 progress: Callable[[int], None] | None = None) -> None:
        """Download to `dest` (through a temporary file next to it); refuses bytes whose SHA-256 differs."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".restoring")
        for attempt in range(3):
            _, _, r = self._call("GET", key, stream=True)
            h = hashlib.sha256()
            got = 0
            try:
                with open(tmp, "wb") as f:
                    while True:
                        b = r.read(BLOCK)
                        if not b:
                            break
                        f.write(b)
                        h.update(b)
                        got += len(b)
                        if progress:
                            progress(len(b))
                    f.flush()
                    os.fsync(f.fileno())
            except OSError:
                tmp.unlink(missing_ok=True)
                if attempt == 2:
                    raise
                continue
            finally:
                close = getattr(r, "close", None)
                if close:
                    close()
            if got == size and h.hexdigest() == sha256:
                os.replace(tmp, dest)
                return
            tmp.unlink(missing_ok=True)
        raise R2Error(f"{key}: the downloaded bytes do not match")

    def delete(self, key: str) -> None:
        self._call("DELETE", key, ok=(200, 204, 404))

    def keys(self, prefix: str = "") -> Iterator[dict]:
        """Every object under `prefix`: {key, size, modified (epoch seconds)}."""
        token = None
        while True:
            q = {"list-type": "2", "prefix": prefix}
            if token:
                q["continuation-token"] = token
            _, _, out = self._call("GET", "", q)
            root = ElementTree.fromstring(out)
            ns = _NS if root.tag.startswith(_NS) else ""
            for c in root.iter(f"{ns}Contents"):
                mod = c.findtext(f"{ns}LastModified") or ""
                try:
                    ts = datetime.strptime(mod[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
                except ValueError:
                    ts = 0.0
                yield {"key": c.findtext(f"{ns}Key"), "size": int(c.findtext(f"{ns}Size") or 0), "modified": ts}
            if (root.findtext(f"{ns}IsTruncated") or "").lower() != "true":
                return
            token = root.findtext(f"{ns}NextContinuationToken")
            if not token:
                return
