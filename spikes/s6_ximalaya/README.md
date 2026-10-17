# Spike S6 — Can LACUNA publish to 喜马拉雅 by itself?

Status (2026-10-17): code + offline tests done; **waiting for Leon to log in once on his PC** to run it
against the real site. Not part of the App and not in a release batch.

## Finding 1: no official upload API for a personal creator

- The open platform (open.ximalaya.com) only documents content *consumption / distribution* APIs:
  免费点播内容 API, 付费点播内容 API, 内容运营 API, 账号 API, 分销接口 — for companies building players,
  car apps and smart speakers. None of them uploads a track into a creator's album.
- An open-source uploader that does the same job (github.com/yezi5yue/ximalaya-bulk-uploader, MIT)
  reached the same conclusion and drives the web page with Playwright.
- So the "API" option that is left is replaying the creator center's **internal** endpoints with
  Leon's login cookie. That is undocumented, can change without notice, and its signing scheme is
  unknown. `--capture` below records which endpoints the page calls (method, path, field names; no
  values) so we can judge it with facts after one real run. Default plan: Playwright.

## Finding 2: the web upload flow (from the open-source uploader, to be confirmed on Leon's account)

Page `https://www.ximalaya.com/reform-upload/page/webCenter/upload` (login at studio.ximalaya.com):

1. Click 「上传音频」 → native file chooser → file uploads in the background (「上传中」).
2. 专辑: a select button + scrolling list with 「加载更多」.
3. 标题: `input[placeholder='请输入声音标题']`.
4. 简介: a KindEditor rich-text box (HTML; newlines must become `<br>`).
5. 权限设置: radio 公开 / 私密 / 粉丝; **defaults to 公开**.
6. Checkbox 「我已阅读并同意《知识产权承诺》」; 「确认发布」 stays disabled until it is ticked.
7. Success → URL contains `uploadSuccess`.

Known risks: hashed CSS class names change with site releases (the script matches on text and
class prefixes instead); the site has rate limiting / captcha on repeated uploads (the script stops
when it sees one); 1–2 h WAV files are 0.6–1.3 GB, upload size limit is unknown (`probe` reads the
page's hint text).

## What the script does — `xmly.py`

| Command | What happens | Publishes? |
|---|---|---|
| `login` | Opens a browser window on studio.ximalaya.com; Leon logs in himself (he uses 微信 third-party login: click the WeChat icon, scan the QR with WeChat on his phone). Login is kept in a browser profile on his PC (`%LOCALAPPDATA%\LACUNA\xmly_profile`). | No |
| `probe` | Opens the upload page, lists form labels / buttons / file-size hints, screenshot. | No |
| `draft` | Uploads a 20 s test tone, picks the album, fills title + description, sets **私密**, then **stops before 确认发布**; window stays open. | **No** |
| `publish-private` | Same, then clicks 确认发布 — refuses unless 私密 is verified. Only with Leon's OK. | Private only |

Safety: no cookie/token/password is printed, stored in the repo or sent anywhere; the browser
is Leon's installed Edge (no download). Outputs go to `./xmly_poc_out/` (screenshots, JSON report,
`*_endpoints.json`).

Tests: `tests/test_s6_ximalaya.py` — helpers (description HTML, login detection, capture redaction)
everywhere; the full form flow against `fake_upload.html` where Python Playwright + Chromium exist
(skipped in CI).

## Run on Leon's PC (needs Leon present for the login)

Separate folder and Python env, so the App is untouched:

```bat
mkdir C:\Projects\LACUNA_Workspace\xmly_poc
cd C:\Projects\LACUNA_Workspace\xmly_poc
copy <repo>\spikes\s6_ximalaya\xmly.py .
py -3.12 -m venv .venv
.venv\Scripts\pip install playwright numpy soundfile
.venv\Scripts\python xmly.py login
.venv\Scripts\python xmly.py probe --capture
.venv\Scripts\python xmly.py draft --album 洛城二三事 --capture
rem only after Leon says OK, private:
.venv\Scripts\python xmly.py publish-private --album 洛城二三事 --capture
```

After a private test publish, Leon deletes the test track in 创作中心 (or we automate that next).

## Results on the real site

_To fill in after the run: probe output, whether draft filled every field, endpoint shapes, upload
size limit, whether the description keeps line breaks, any captcha._
