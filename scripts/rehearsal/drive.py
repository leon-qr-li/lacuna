"""Drive a running rehearsal server (scripts/rehearsal/serve.py) through the whole episode flow
after the import, timing every call: review, chat, undo/redo, music, export, publish pack,
cover, upload page. Prints one line per step and writes a JSON log.

    python scripts/rehearsal/drive.py <episode-id> [--url http://127.0.0.1:8790] [--log out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

LOG: list[dict] = []


def step(name: str, fn, *a, **kw):
    t = time.monotonic()
    try:
        out = fn(*a, **kw)
        ok, err = True, None
    except Exception as e:      # noqa: BLE001
        out, ok, err = None, False, f"{type(e).__name__}: {e}"
    dt = round(time.monotonic() - t, 2)
    LOG.append({"step": name, "ok": ok, "seconds": dt, "error": err})
    print(f"{'OK ' if ok else 'ERR'} {dt:8.2f}s  {name}" + (f"  -> {err}" if err else ""), flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("--url", default="http://127.0.0.1:8790")
    ap.add_argument("--log", type=Path, default=None)
    ap.add_argument("--music-dir", type=Path, default=None, help="folder of music files to put in the library")
    a = ap.parse_args()
    c = httpx.Client(base_url=a.url, timeout=600)
    E = f"/api/episodes/{a.episode}"

    def j(method, path, **kw):
        r = c.request(method, path, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:300]}")
        return r.json() if "json" in r.headers.get("content-type", "") else r

    def poll(path, key, done=("done",), fail=("error",), every=2.0, limit=3600):
        t0 = time.monotonic()
        while time.monotonic() - t0 < limit:
            v = j("GET", path)
            s = v.get(key)
            state = (s or {}).get("state") if isinstance(s, dict) else None
            if state is None or state in done:
                return v
            if state in fail:
                raise RuntimeError(f"{path}: {s.get('error')}")
            time.sleep(every)
        raise TimeoutError(path)

    ep = step("打开剧集 (summary)", j, "GET", E)
    size = len(json.dumps(ep, ensure_ascii=False).encode())
    edits = ep["edits"]
    print(f"     summary {size / 1e6:.1f} MB, {len(edits)} edits, "
          f"{sum(1 for e in edits if e.get('consequential'))} to review, duration {ep.get('duration')}s")
    ver = ep["version"]

    def seek(at_s):
        hdr = j("GET", f"{E}/audio/{ver}.wav", headers={"range": "bytes=0-43"})
        sr = int.from_bytes(hdr.content[24:28], "little")
        ch = int.from_bytes(hdr.content[22:24], "little")
        off = 44 + int(at_s * sr) * 2 * ch
        r = j("GET", f"{E}/audio/{ver}.wav", headers={"range": f"bytes={off}-{off + sr * 2 * ch * 5}"})
        return len(r.content)
    step("试听：从开头播放 5 秒", seek, 0)
    step("试听：跳到 1:50:00 播放 5 秒", seek, 6600)
    step("试听：跳到最后 1 分钟", seek, max(0, (ep.get("duration") or 60) - 60))

    pend = [e for e in edits if e.get("consequential") and e.get("review") in (None, "pending")] or \
           [e for e in edits if e.get("consequential")]
    if pend:
        e0 = pend[0]
        step("单个改动 A/B 试听", j, "GET", f"{E}/edits/{e0['id']}/ab")
        step("单个改动原文", j, "GET", f"{E}/edits/{e0['id']}/text")
        for k, e in enumerate(pend[1:6]):
            step(f"审阅：保留第 {k + 1} 个", j, "POST", f"{E}/edits/{e['id']}/review", json={"action": "keep", "playhead": 10})
        for k, e in enumerate(pend[6:9]):
            step(f"审阅：恢复第 {k + 1} 个", j, "POST", f"{E}/edits/{e['id']}/review", json={"action": "restore", "playhead": 10})
        late = [e for e in pend if (e.get("at") or 0) > 6000][:1]
        if late:
            step("审阅：恢复 1:40 之后的一个", j, "POST", f"{E}/edits/{late[0]['id']}/review",
                 json={"action": "restore", "playhead": late[0].get("at")})
    step("撤销", j, "POST", f"{E}/undo", json={"playhead": 10})
    step("重做", j, "POST", f"{E}/redo", json={"playhead": 10})
    ch = step("AI 对话：在 1:30:00 处说「这句删掉」", j, "POST", f"{E}/chat", json={"text": "这句删掉", "playhead": 5400})
    pid = (ch or {}).get("proposal", {}).get("id") if ch else None
    if pid:
        step("AI 对话：A/B 试听提案", j, "GET", f"{E}/proposals/{pid}/ab")
        step("AI 对话：批准提案", j, "POST", f"{E}/proposals/{pid}/approve", json={"playhead": 5400})
    step("审阅：其余全部批准", j, "POST", f"{E}/review", json={"action": "approve", "playhead": 10})
    ep = step("重新打开剧集", j, "GET", E)
    if ep:
        print(f"     after review: duration {ep.get('duration')}s, pending {ep.get('pending_review')}")
        ver = ep["version"]
        step("试听（审阅后）：跳到 1:20:00", seek, 4800)

    # ---------------- music
    if a.music_dir and a.music_dir.is_dir():
        ids = {}
        for f in sorted(a.music_dir.iterdir()):
            kind = "intro" if "片头" in f.name else "outro" if "片尾" in f.name else "interlude"
            r = step(f"素材库：上传 {f.name}", j, "POST", "/api/library/upload",
                     params={"name": f.name, "kind": kind, "note": "测试音乐"},
                     content=f.read_bytes(), headers={"content-type": "application/octet-stream"})
            if r:
                ids[kind] = r["asset"]["id"]
        if ids:
            dur = (ep or {}).get("duration") or 3600
            for role, kw in (("intro", {}), ("interlude", {"at_s": 3600}), ("outro", {})):
                if role in ids:
                    step(f"配乐：{role}", j, "POST", f"{E}/music", json={"asset_id": ids[role], "role": role, **kw})
            m = step("配乐：读回", j, "GET", f"{E}/music")
            if m:
                for p in m.get("placements", [])[:3]:
                    step(f"配乐：试听 {p.get('role')}", j, "GET", f"{E}/music/{p['id']}/preview")
                mk = m.get("mix_version")
                if mk:
                    def mix_seek():
                        r = j("GET", f"{E}/mix/{mk}.wav", headers={"range": "bytes=0-43"})
                        sr = int.from_bytes(r.content[24:28], "little")
                        chn = int.from_bytes(r.content[22:24], "little")
                        off = 44 + int(dur * 0.9 * sr) * 2 * chn
                        return len(j("GET", f"{E}/mix/{mk}.wav", headers={"range": f"bytes={off}-{off + sr * 2 * chn * 5}"}).content)
                    step("配乐：成品混音跳到 90% 处", mix_seek)

    # ---------------- export
    step("导出：开始 (WAV + MP3)", j, "POST", f"{E}/export", json={"formats": ["wav", "mp3"]})
    ex = step("导出：等待完成", poll, f"{E}/export", "job", every=5)
    if ex:
        res = ex["job"]["result"]
        print(f"     export: {res['files']}  report={json.dumps(res['report'], ensure_ascii=False)[:400]}")
        if res.get("errors"):
            print(f"     export errors: {res['errors']}")

    # ---------------- publish pack, cover, upload page
    step("发布资料：生成", j, "POST", f"{E}/publish/generate")
    pub = step("发布资料：等待完成", poll, f"{E}/publish", "job", every=2)
    if pub:
        print(f"     publish: title={pub.get('title') or (pub.get('pack') or {}).get('title')}")
    step("发布资料：重新对时间", j, "POST", f"{E}/publish/retime")
    step("海报：生成", j, "POST", f"{E}/poster/generate")
    po = step("海报：等待完成", poll, f"{E}/poster", "job", every=2)
    if po:
        vs = [v for v in po.get("variants", []) if v.get("png") or v.get("state") == "done"]
        if vs:
            step("海报：选定", j, "POST", f"{E}/poster/{vs[0]['id']}/choose")
    up = step("上传喜马拉雅页", j, "GET", f"{E}/upload")
    if up:
        print("     upload:", json.dumps(up, ensure_ascii=False)[:1500])
    step("上传喜马拉雅页：下载封面", j, "GET", f"{E}/upload/cover.jpg")

    bad = [s for s in LOG if not s["ok"]]
    print(f"\n{len(LOG) - len(bad)}/{len(LOG)} steps OK")
    if a.log:
        a.log.write_text(json.dumps(LOG, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
