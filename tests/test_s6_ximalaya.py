"""S6 喜马拉雅 publish POC: helpers + the form filler against a fake upload page.

The browser test runs only where Python Playwright and a Chromium are installed
(not in CI); the pure-helper tests run everywhere.
"""
import importlib.util
import json
import os
import shutil
from argparse import Namespace
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPIKE = HERE.parent / "spikes" / "s6_ximalaya"


@pytest.fixture(scope="module")
def X():
    spec = importlib.util.spec_from_file_location("s6_xmly", SPIKE / "xmly.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_desc_to_html_keeps_lines_and_escapes(X):
    assert X.desc_to_html("a<b>\r\n第二行 & 三") == "a&lt;b&gt;<br>第二行 &amp; 三"


def test_is_blocked(X):
    assert X.is_blocked("……请完成安全验证……")
    assert not X.is_blocked("上传音频")
    assert not X.is_blocked("")


def test_is_logged_in_looks_at_token_cookie_names_only(X):
    assert X.is_logged_in([{"domain": ".ximalaya.com", "name": "1&_token", "value": "x"}])
    assert not X.is_logged_in([{"domain": ".ximalaya.com", "name": "_xmLog", "value": "x"}])
    assert not X.is_logged_in([{"domain": ".ximalaya.com", "name": "1&_token", "value": ""}])
    assert not X.is_logged_in([{"domain": ".example.com", "name": "token", "value": "x"}])


def test_summarize_requests_drops_every_value(X):
    reqs = [
        {"method": "POST", "url": "https://www.ximalaya.com/upload/api/track/save?token=SECRET1&albumId=42",
         "resource_type": "xhr", "content_type": "application/json;charset=UTF-8",
         "post_data": json.dumps({"title": "SECRET2", "albumId": 42, "isPublic": False}), "status": 200},
        {"method": "POST", "url": "https://www.ximalaya.com/upload/api/track/save?token=SECRET3&albumId=42",
         "resource_type": "xhr", "content_type": "application/json", "post_data": "{}", "status": 500},
        {"method": "POST", "url": "https://upload.ximalaya.com/clamper-server/mkblk/1",
         "resource_type": "xhr", "content_type": "multipart/form-data; boundary=x", "post_data": "<binary>",
         "status": 200},
        {"method": "GET", "url": "https://s1.xmcdn.com/app.js", "resource_type": "script",
         "content_type": "", "post_data": None, "status": 200},
        {"method": "POST", "url": "https://analytics.example.com/beacon", "resource_type": "xhr",
         "content_type": "text/plain", "post_data": "SECRET4", "status": 204},
    ]
    out = X.summarize_requests(reqs)
    text = json.dumps(out, ensure_ascii=False)
    assert "SECRET" not in text
    save = next(e for e in out if "track/save" in e["url"])
    assert save["url"].endswith("?token=…&albumId=…")
    assert save["count"] == 2 and save["statuses"] == [200, 500]
    assert save["body_fields"] == ["albumId", "isPublic", "title"]
    assert any(e["body_fields"] == "multipart(binary upload)" for e in out)
    assert len(out) == 2  # static asset and foreign beacon left out
    X.assert_no_secrets(out)
    with pytest.raises(ValueError):
        X.assert_no_secrets([{"h": "Cookie: a=b"}])


def test_make_test_wav(X, tmp_path):
    import soundfile as sf

    p = X.make_test_wav(tmp_path / "t.wav", seconds=1.0)
    data, sr = sf.read(str(p))
    assert sr == 44100 and data.shape == (44100, 2)
    assert 0.05 < abs(data).max() <= 0.11


def test_profile_dir_is_outside_repo(X):
    assert HERE.parent not in X.default_profile_dir().parents


def _chromium():
    for c in (os.environ.get("XMLY_BROWSER_EXE"), "/opt/pw-browsers/chromium", shutil.which("chromium")):
        if c and Path(c).exists():
            return c
    return None


@pytest.fixture()
def page():
    pw_api = pytest.importorskip("playwright.sync_api")
    exe = _chromium()
    if not exe:
        pytest.skip("no Chromium for the browser test")
    with pw_api.sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=exe, headless=True)
        yield b.new_page()
        b.close()


def _args(X, **kw):
    a = dict(upload_url=(SPIKE / "fake_upload.html").as_uri(), album="洛城二三事",
             title=X.TEST_TITLE, desc=X.TEST_DESC, upload_timeout=10)
    a.update(kw)
    return Namespace(**a)


def test_draft_fills_everything_and_never_publishes(X, page, tmp_path):
    rep = X.fill_form(page, _args(X), X.make_test_wav(tmp_path / "t.wav", 1.0))
    assert rep.get("ready"), rep
    assert page.locator("#album-picked").inner_text() == "洛城二三事"  # found after 加载更多
    assert page.locator("input[placeholder='请输入声音标题']").input_value() == X.TEST_TITLE
    assert page.locator("#soundRichIntro").input_value() == X.desc_to_html(X.TEST_DESC)
    assert X._is_private(page)
    assert page.evaluate("window.__published") == 0
    assert "确认发布" in rep["inventory"]["buttons"]
    assert any("2GB" in h for h in rep["inventory"]["hints"])


def test_missing_album_stops_before_filling(X, page, tmp_path):
    rep = X.fill_form(page, _args(X, album="不存在的专辑"), X.make_test_wav(tmp_path / "t.wav", 1.0))
    assert not rep.get("ready")
    assert rep["steps"][-1]["step"] == "album"
    assert page.evaluate("window.__published") == 0


def test_publish_private_refuses_when_public(X, page, tmp_path):
    X.fill_form(page, _args(X), X.make_test_wav(tmp_path / "t.wav", 1.0))
    page.locator("label.ant-radio-wrapper", has_text="公开").click()
    res = X.publish_private(page)
    assert not res["ok"] and "私密" in res["reason"]
    assert page.evaluate("window.__published") == 0


def test_publish_private_clicks_once_private(X, page, tmp_path):
    X.fill_form(page, _args(X), X.make_test_wav(tmp_path / "t.wav", 1.0))
    res = X.publish_private(page)
    assert res["ok"], res
    assert page.locator("#agree").is_checked()
    assert page.evaluate("window.__published") == 1
