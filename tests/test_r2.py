"""The small R2 client (lacuna_app/r2.py): AWS Signature V4 against AWS's own example, uploads in one go and in
parts, downloads that refuse changed bytes, listing."""
import hashlib
import io
from datetime import datetime, timezone

import pytest

from lacuna_app import r2
from lacuna_app.r2 import Bucket, R2Error, sign


def test_signature_matches_the_aws_example():
    # docs.aws.amazon.com/AmazonS3/latest/API/sig-v4-header-based-auth.html, "GET Object"
    h = sign("GET", "examplebucket.s3.amazonaws.com", "/test.txt", {}, {"Range": "bytes=0-9"}, r2.EMPTY,
             "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
             datetime(2013, 5, 24, tzinfo=timezone.utc), region="us-east-1")
    assert h["Authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")


class FakeR2(Bucket):
    def __init__(self):
        super().__init__("https://acct.r2.cloudflarestorage.com/audio", "kid", "secret", sleep=lambda s: None)
        self.store: dict[str, tuple[bytes, dict]] = {}
        self.uploads: dict[str, dict[int, bytes]] = {}
        self.calls = []
        self.drop_next = 0

    def send(self, method, url, headers, body=None, stream=False):
        from urllib.parse import parse_qs, unquote, urlsplit
        u = urlsplit(url)
        key = unquote(u.path).split("/", 2)[2] if u.path.count("/") >= 2 else ""
        q = {k: v[0] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
        self.calls.append((method, key, q))
        assert headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=kid/")
        if self.drop_next:
            self.drop_next -= 1
            return 503, {}, b""
        data = body.read() if hasattr(body, "read") else (body or b"")
        if data and method == "PUT":
            assert hashlib.sha256(data).hexdigest() == headers["x-amz-content-sha256"]
        if method == "PUT" and "partNumber" in q:
            self.uploads[q["uploadId"]][int(q["partNumber"])] = data
            return 200, {"ETag": f'"p{q["partNumber"]}"'}, b""
        if method == "PUT":
            self.store[key] = (data, {"x-amz-meta-sha256": headers.get("x-amz-meta-sha256")})
            return 200, {}, b""
        if method == "POST" and "uploads" in q:
            self.uploads["U1"] = {}
            self.meta = {"x-amz-meta-sha256": headers.get("x-amz-meta-sha256")}
            return 200, {}, b"<InitiateMultipartUploadResult><UploadId>U1</UploadId></InitiateMultipartUploadResult>"
        if method == "POST" and "uploadId" in q:
            parts = self.uploads.pop(q["uploadId"])
            self.store[key] = (b"".join(parts[n] for n in sorted(parts)), self.meta)
            return 200, {}, b"<CompleteMultipartUploadResult/>"
        if method == "HEAD":
            if key not in self.store:
                return 404, {}, b""
            d, m = self.store[key]
            return 200, {"Content-Length": str(len(d)), **m}, b""
        if method == "GET" and key:
            return 200, {}, io.BytesIO(self.store[key][0])
        if method == "GET":
            items = "".join(f"<Contents><Key>{k}</Key><Size>{len(v[0])}</Size>"
                            f"<LastModified>2026-10-01T00:00:00.000Z</LastModified></Contents>" for k, v in self.store.items())
            return 200, {}, (f'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">{items}'
                             f"<IsTruncated>false</IsTruncated></ListBucketResult>").encode()
        if method == "DELETE":
            self.store.pop(key, None)
            return 204, {}, b""
        raise AssertionError((method, url))


def test_put_get_head_delete_list(tmp_path):
    b = FakeR2()
    f = tmp_path / "Leon.wav"
    f.write_bytes(b"RIFF" + bytes(range(256)) * 100)
    sha = r2.file_sha256(f)
    b.drop_next = 1                     # one 503 on the way: tried again
    b.put_file("audio/" + sha, f, sha)
    assert b.exists("audio/" + sha, f.stat().st_size, sha)
    assert not b.exists("audio/" + sha, 1, sha)
    out = tmp_path / "back" / "Leon.wav"
    b.get_file("audio/" + sha, out, sha, f.stat().st_size)
    assert out.read_bytes() == f.read_bytes()
    assert [o["key"] for o in b.keys("audio/")] == ["audio/" + sha]
    b.delete("audio/" + sha)
    assert b.head("audio/" + sha) is None


def test_big_files_go_up_in_parts(tmp_path, monkeypatch):
    monkeypatch.setattr(r2, "ONE_SHOT", 1000)
    monkeypatch.setattr(r2, "PART", 400)
    b = FakeR2()
    f = tmp_path / "long.wav"
    f.write_bytes(bytes(range(256)) * 9)          # 2304 bytes: 6 parts
    sha = r2.file_sha256(f)
    b.put_file("audio/x", f, sha)
    assert b.store["audio/x"][0] == f.read_bytes()
    assert sum(1 for m, _k, q in b.calls if "partNumber" in q) == 6


def test_a_download_with_other_bytes_is_refused(tmp_path):
    b = FakeR2()
    b.store["audio/y"] = (b"changed", {})
    with pytest.raises(R2Error):
        b.get_file("audio/y", tmp_path / "y.wav", hashlib.sha256(b"original").hexdigest(), 7)
    assert not (tmp_path / "y.wav").exists() and not list(tmp_path.iterdir())


def test_settings_come_from_the_environment():
    assert Bucket.from_env({}) is None
    b = Bucket.from_env({"LACUNA_AUDIO_STORE": "https://a.r2.cloudflarestorage.com/lacuna-audio",
                         "LACUNA_AUDIO_KEY_ID": "k", "LACUNA_AUDIO_SECRET": "s"})
    assert (b.host, b.bucket) == ("a.r2.cloudflarestorage.com", "lacuna-audio")
    with pytest.raises(R2Error):
        Bucket("http://a/b", "k", "s")
