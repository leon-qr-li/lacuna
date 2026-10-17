# 喜马拉雅: no upload API for personal creators, so Leon uploads by hand from a ready page

- Date: 2026-10-17
- Status: Leon 决定 ("API 这条路不行，那就算了……我自己来弄"), after Claude checked the API
- Changes: settles D20 — no automatic publishing, no browser automation; phase 11 is a "上传喜马拉雅" page

open.ximalaya.com documents only consumption / distribution APIs (免费/付费点播内容, 内容运营, 账号, 分销) for
companies building players; none uploads into a creator's album. The only automatic route would be driving the
creator-center web page (Playwright, as the open-source yezi5yue/ximalaya-bulk-uploader does) or replaying its
undocumented internal endpoints with Leon's login. Leon chose not to: the App prepares everything (WAV, title,
blurb, show notes, cover) on one page in the order of the upload form, and he uploads himself.
Don't re-investigate unless 喜马拉雅 announces a creator upload API.
