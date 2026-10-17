# 喜马拉雅 has no upload API for personal creators; automate the web page instead

- Date: 2026-10-17
- Status: Claude 技术结论 (Leon asked for an API POC, Playwright as fallback)
- Changes: resolves the "official API TBD" half of D20; browser automation half is being verified (spike S6)

open.ximalaya.com documents only consumption / distribution APIs (免费/付费点播内容, 内容运营, 账号, 分销) for
companies; none uploads into a creator's album. An open-source uploader (yezi5yue/ximalaya-bulk-uploader) drives
the creator-center upload page with Playwright for the same reason. Replaying the page's internal endpoints with
Leon's cookie is undocumented and possibly signed; `xmly.py --capture` records their shapes so we can judge it
with facts. Until then the path is Playwright: Leon logs in himself (WeChat QR) in a local browser profile, the
script fills the form, publishing stays behind Leon's explicit OK.
