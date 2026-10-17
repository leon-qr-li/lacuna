"""Spike S6: can LACUNA publish an episode to 喜马拉雅 by itself?

Ximalaya has no upload API for personal creators (the open platform at
open.ximalaya.com is a content *distribution* API for companies), so this POC
drives the creator-center web page with Playwright, the same page Leon uses.

Safety rules baked into the code:
  * Leon logs in himself, in a visible browser window. The login lives in a
    browser profile folder on his PC; no cookie, token or password is ever
    printed, saved to the repo, or sent anywhere.
  * `draft` fills the upload form (test audio, title, description, album,
    权限 = 私密) and STOPS before 确认发布. Nothing is published.
  * `publish-private` is the only command that clicks 确认发布, and it refuses
    to unless 私密 is verified checked. Run it only after Leon says OK.
  * `--capture` records which internal endpoints the page calls (method, path,
    field names only; header and body values are dropped) so we can judge
    whether a direct-HTTP "API" path is worth it.

Usage (on Leon's PC, from the repo root or anywhere with playwright installed):
  python xmly.py login                      # opens a window; Leon logs in
  python xmly.py probe  --capture           # reads the upload page, no upload
  python xmly.py draft  --album 洛城二三事 --capture
  python xmly.py publish-private --album 洛城二三事   # only after Leon OKs
"""
from __future__ import annotations

import argparse
import html
import json
import os
import random
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

STUDIO_URL = "https://studio.ximalaya.com/"
UPLOAD_URL = "https://www.ximalaya.com/reform-upload/page/webCenter/upload"

TEST_TITLE = "LACUNA 自动发布测试（请勿收听）"
TEST_DESC = "这是 LACUNA 自动发布 POC 的测试音频。\n第二行：检查换行是否保留。\n会在测试后删除。"

# Text the platform shows when it throttles or challenges the session.
BLOCK_TEXTS = (
    "验证码", "安全验证", "请完成安全验证", "操作过于频繁", "访问受限",
    "人机验证", "网络异常请稍后重试", "您的操作过于频繁",
)


# ---------------------------------------------------------------- pure helpers

def default_profile_dir() -> Path:
    """Browser profile with Leon's login. Kept outside the repo and the workspace."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "LACUNA" / "xmly_profile"
    return Path.home() / ".lacuna" / "xmly_profile"


def desc_to_html(text: str) -> str:
    """The description box is a KindEditor (HTML); plain newlines would collapse."""
    return html.escape(text, quote=False).replace("\r\n", "\n").replace("\n", "<br>")


def is_blocked(page_text: str) -> bool:
    return any(k in (page_text or "") for k in BLOCK_TEXTS)


def is_logged_in(cookies: list[dict]) -> bool:
    """Ximalaya sets a 1&_token-style cookie after login. Only names are inspected."""
    for c in cookies:
        name = c.get("name", "").lower()
        if "ximalaya" in c.get("domain", "") and "token" in name and c.get("value"):
            return True
    return False


def _redact_query(url: str) -> str:
    parts = urlsplit(url)
    keys = []
    for kv in parts.query.split("&") if parts.query else []:
        k = kv.split("=", 1)[0]
        keys.append(k)
    q = ("?" + "&".join(f"{k}=…" for k in keys)) if keys else ""
    return f"{parts.scheme}://{parts.netloc}{parts.path}{q}"


def _body_shape(post: str | None, content_type: str) -> list[str] | str | None:
    """Field names of a request body, never values."""
    if not post:
        return None
    ct = (content_type or "").lower()
    if "json" in ct:
        try:
            obj = json.loads(post)
        except ValueError:
            return "json(unparsed)"
        return sorted(obj.keys()) if isinstance(obj, dict) else type(obj).__name__
    if "x-www-form-urlencoded" in ct:
        return sorted({kv.split("=", 1)[0] for kv in post.split("&") if kv})
    if "multipart" in ct:
        return "multipart(binary upload)"
    return f"{ct or 'unknown'}({len(post)} bytes)"


def summarize_requests(reqs: list[dict]) -> list[dict]:
    """Collapse captured requests into endpoint shapes, dropping every value.

    Each input dict: method, url, resource_type, content_type, post_data, status.
    Static assets and analytics beacons are left out.
    """
    out: dict[tuple, dict] = {}
    for r in reqs:
        if r.get("resource_type") not in ("xhr", "fetch", "document"):
            continue
        host = urlsplit(r["url"]).netloc
        if not host.endswith(("ximalaya.com", "xmcdn.com")):
            continue
        key = (r["method"], _redact_query(r["url"]))
        e = out.setdefault(key, {
            "method": r["method"], "url": key[1], "count": 0,
            "body_fields": _body_shape(r.get("post_data"), r.get("content_type", "")),
            "statuses": [],
        })
        e["count"] += 1
        st = r.get("status")
        if st is not None and st not in e["statuses"]:
            e["statuses"].append(st)
    return list(out.values())


def assert_no_secrets(obj) -> None:
    """Last line of defence before writing a capture file: no header dumps."""
    text = json.dumps(obj, ensure_ascii=False)
    for word in ("Cookie:", "Authorization:", "Set-Cookie"):
        if word.lower() in text.lower():
            raise ValueError(f"capture contains {word}")


def make_test_wav(path: Path, seconds: float = 20.0, sr: int = 44100) -> Path:
    """A quiet 440/660 Hz two-tone test file, clearly not an episode."""
    import numpy as np
    import soundfile as sf

    t = np.arange(int(seconds * sr)) / sr
    tone = np.where((t % 2.0) < 1.0, np.sin(2 * np.pi * 440 * t), np.sin(2 * np.pi * 660 * t))
    fade = np.minimum(1.0, np.minimum(t, seconds - t) / 0.2)
    data = (0.1 * tone * fade).astype("float32")
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.stack([data, data], axis=1), sr, subtype="PCM_16")
    return path


# ---------------------------------------------------------------- browser part

def _launch(pw, profile: Path, headless: bool):
    """Leon's installed Edge on Windows (no browser download); bundled Chromium elsewhere."""
    profile.mkdir(parents=True, exist_ok=True)
    kw = dict(user_data_dir=str(profile), headless=headless, viewport={"width": 1400, "height": 900},
              locale="zh-CN")
    channel = os.environ.get("XMLY_BROWSER_CHANNEL", "msedge" if os.name == "nt" else "")
    exe = os.environ.get("XMLY_BROWSER_EXE")
    if exe:
        kw["executable_path"] = exe
    elif channel:
        kw["channel"] = channel
    return pw.chromium.launch_persistent_context(**kw)


class Capture:
    def __init__(self, page):
        self.reqs: list[dict] = []
        page.on("requestfinished", self._on)
        page.on("requestfailed", self._on)

    def _on(self, req):
        try:
            resp = req.response()
            status = resp.status if resp else None
        except Exception:
            status = None
        try:
            post = req.post_data
        except Exception:  # binary bodies
            post = "<binary>"
        self.reqs.append({
            "method": req.method, "url": req.url, "resource_type": req.resource_type,
            "content_type": req.headers.get("content-type", ""), "post_data": post, "status": status,
        })

    def write(self, path: Path):
        summary = summarize_requests(self.reqs)
        assert_no_secrets(summary)
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[capture] {len(summary)} endpoints -> {path}")


def _page_text(page) -> str:
    try:
        return page.evaluate("() => document.body.innerText") or ""
    except Exception:
        return ""


def _human_pause(page, lo=600, hi=1600):
    page.wait_for_timeout(random.randint(lo, hi))


def cmd_login(page, ctx, args) -> int:
    page.goto(args.studio_url, timeout=60000)
    print("请在打开的窗口里登录喜马拉雅（点微信图标，用手机微信扫码）。登录好后这里会自动继续，最多等 5 分钟。")
    deadline = time.time() + 300
    while time.time() < deadline:
        if is_logged_in(ctx.cookies()):
            print("LOGIN_OK 登录成功，登录状态保存在本机：", args.profile)
            return 0
        page.wait_for_timeout(2000)
    print("LOGIN_TIMEOUT 5 分钟内没检测到登录。")
    return 1


def _open_upload_form(page, args, audio: Path):
    page.goto(args.upload_url, timeout=60000)
    _human_pause(page, 3000, 4500)
    pick = page.locator("div.webuploader-pick", has_text="上传音频").first
    pick.wait_for(timeout=20000)
    with page.expect_file_chooser(timeout=10000) as fc:
        pick.click()
    fc.value.set_files(str(audio))
    page.locator("input[placeholder='请输入声音标题']").wait_for(timeout=30000)


def _wait_upload_done(page, timeout_s: int) -> bool:
    for _ in range(max(1, timeout_s // 2)):
        if "上传中" not in _page_text(page):
            return True
        page.wait_for_timeout(2000)
    return False


def _select_album(page, album: str) -> dict:
    btn = page.locator("button[class*='search-select-album-btn']").first
    if btn.count() == 0:
        return {"ok": False, "reason": "album selector button not found"}
    btn.click()
    _human_pause(page, 600, 1000)
    item = page.locator("[class*='scroll-item-content']", has_text=album).first
    for _ in range(15):
        if item.count() > 0:
            break
        more = page.get_by_text("加载更多").first
        if more.count() == 0:
            break
        more.click()
        page.wait_for_timeout(700)
    if item.count() == 0:
        return {"ok": False, "reason": f"album '{album}' not in list"}
    item.click()
    return {"ok": True}


def _set_title(page, title: str):
    inp = page.locator("input[placeholder='请输入声音标题']").first
    inp.click()
    inp.fill(title)


def _set_description(page, text: str) -> dict:
    return page.evaluate(
        """(h) => {
            const KE = window.KindEditor;
            const ed = KE && KE.instances ? KE.instances[0] : null;
            if (!ed) return {ok:false, reason:'KindEditor not found'};
            ed.html(h);
            try { ed.sync(); } catch (e) {}
            return {ok:true};
        }""",
        desc_to_html(text),
    )


def _set_private(page) -> dict:
    """Click 私密 inside the 权限设置 row and verify it stuck. The page defaults to 公开."""
    return page.evaluate(
        """() => {
            const row = Array.from(document.querySelectorAll('.ant-form-item'))
              .find(it => { const l = it.querySelector('.ant-form-item-label'); return l && /权限设置/.test(l.innerText); });
            if (!row) return {ok:false, reason:'权限设置 row not found'};
            const label = Array.from(row.querySelectorAll('label.ant-radio-wrapper'))
              .find(l => l.innerText.trim().startsWith('私密'));
            if (!label) return {ok:false, reason:'私密 option not found'};
            label.click();
            const dot = label.querySelector('.ant-radio');
            const on = dot ? dot.classList.contains('ant-radio-checked') : label.querySelector('input').checked;
            return on ? {ok:true} : {ok:false, reason:'私密 did not become checked'};
        }"""
    )


def _is_private(page) -> bool:
    return bool(page.evaluate(
        """() => {
            const row = Array.from(document.querySelectorAll('.ant-form-item'))
              .find(it => { const l = it.querySelector('.ant-form-item-label'); return l && /权限设置/.test(l.innerText); });
            if (!row) return false;
            const on = row.querySelector('label.ant-radio-wrapper-checked');
            return !!on && on.innerText.trim().startsWith('私密');
        }"""
    ))


def _form_inventory(page) -> dict:
    """What the upload page offers: labels, buttons, file hints. Used to plan the real feature."""
    return page.evaluate(
        """() => ({
            url: location.href,
            labels: Array.from(document.querySelectorAll('.ant-form-item-label')).map(e => e.innerText.trim()),
            buttons: Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim()).filter(Boolean),
            hints: (document.body.innerText.match(/[^\\n]*(格式|大小|不超过|MB|GB|小时)[^\\n]*/g) || []).slice(0, 20),
        })"""
    )


def fill_form(page, args, audio: Path) -> dict:
    """Upload the file and fill every field. Never clicks 确认发布."""
    _open_upload_form(page, args, audio)
    report = {"steps": []}

    def step(name, res):
        report["steps"].append({"step": name, **res})
        print(f"[{'ok' if res.get('ok') else 'FAIL'}] {name} {res.get('reason', '')}")
        return res.get("ok")

    if not step("upload", {"ok": _wait_upload_done(page, args.upload_timeout)}):
        return report
    _human_pause(page)
    if not step("album", _select_album(page, args.album)):
        return report
    _set_title(page, args.title)
    step("title", {"ok": True})
    if not step("description", _set_description(page, args.desc)):
        return report
    if not step("private", _set_private(page)):
        return report
    if is_blocked(_page_text(page)):
        step("risk-control", {"ok": False, "reason": "platform showed a captcha / rate-limit page"})
        return report
    report["inventory"] = _form_inventory(page)
    report["ready"] = True
    return report


def _tick_agreement(page):
    page.evaluate(
        """() => {
            const hit = Array.from(document.querySelectorAll('label'))
              .find(el => el.innerText && el.innerText.includes('知识产权承诺'));
            const cb = hit ? hit.querySelector('input[type=checkbox]') : null;
            if (cb && !cb.checked) cb.click();
        }"""
    )


def publish_private(page) -> dict:
    """Click 确认发布 — only when 私密 is verified. Caller must have Leon's OK."""
    if not _is_private(page):
        return {"ok": False, "reason": "refused: 权限设置 is not 私密"}
    _tick_agreement(page)
    _human_pause(page, 800, 2000)
    btn = page.locator("button", has_text="确认发布").first
    for _ in range(4):
        try:
            btn.wait_for(state="visible", timeout=15000)
            btn.click(timeout=10000)
            page.wait_for_url(lambda u: "uploadSuccess" in u, timeout=20000)
            return {"ok": True, "url": page.url}
        except Exception:
            if "发布成功" in _page_text(page):
                return {"ok": True, "url": page.url}
            page.wait_for_timeout(3000)
    return {"ok": False, "reason": "no success page after 4 tries", "url": page.url}


def run(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["login", "probe", "draft", "publish-private"])
    ap.add_argument("--profile", type=Path, default=default_profile_dir())
    ap.add_argument("--out", type=Path, default=Path.cwd() / "xmly_poc_out")
    ap.add_argument("--audio", type=Path, help="audio to upload (default: a 20 s test tone)")
    ap.add_argument("--album", default="洛城二三事")
    ap.add_argument("--title", default=TEST_TITLE)
    ap.add_argument("--desc", default=TEST_DESC)
    ap.add_argument("--capture", action="store_true", help="record endpoint shapes (no values)")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--keep-open", type=int, default=120, help="seconds to leave the window open at the end")
    ap.add_argument("--upload-timeout", type=int, default=1800)
    ap.add_argument("--studio-url", default=STUDIO_URL)
    ap.add_argument("--upload-url", default=UPLOAD_URL)
    args = ap.parse_args(argv)

    from playwright.sync_api import sync_playwright

    args.out.mkdir(parents=True, exist_ok=True)
    audio = args.audio or make_test_wav(args.out / "lacuna_test_tone.wav")
    rc = 0
    with sync_playwright() as pw:
        ctx = _launch(pw, args.profile, args.headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        cap = Capture(page) if args.capture else None
        try:
            if args.command == "login":
                rc = cmd_login(page, ctx, args)
            elif not is_logged_in(ctx.cookies()):
                # Cookies only show up after a visit; check once on the studio page.
                page.goto(args.studio_url, timeout=60000)
                page.wait_for_timeout(2000)
                if not is_logged_in(ctx.cookies()):
                    print("NOT_LOGGED_IN 先运行: python xmly.py login")
                    return 2
            if args.command == "probe":
                page.goto(args.upload_url, timeout=60000)
                page.wait_for_timeout(5000)
                inv = _form_inventory(page)
                inv["blocked"] = is_blocked(_page_text(page))
                (args.out / "probe.json").write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
                page.screenshot(path=str(args.out / "probe.png"), full_page=True)
                print(json.dumps(inv, ensure_ascii=False, indent=2))
            elif args.command in ("draft", "publish-private"):
                rep = fill_form(page, args, audio)
                page.screenshot(path=str(args.out / f"{args.command}_filled.png"), full_page=True)
                if args.command == "publish-private" and rep.get("ready"):
                    rep["publish"] = publish_private(page)
                    print("[publish]", rep["publish"])
                    page.screenshot(path=str(args.out / "publish_result.png"), full_page=True)
                elif rep.get("ready"):
                    print("DRAFT_READY 表单已填好、权限=私密，没有点「确认发布」。窗口保留给你看。")
                (args.out / f"{args.command}.json").write_text(
                    json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
                rc = 0 if rep.get("ready") and rep.get("publish", {"ok": True}).get("ok") else 1
            if not args.headless and args.command != "login":
                page.wait_for_timeout(args.keep_open * 1000)
        finally:
            if cap:
                cap.write(args.out / f"{args.command}_endpoints.json")
            ctx.close()
    return rc


if __name__ == "__main__":
    sys.exit(run())
