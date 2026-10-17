# Spike S6 — 喜马拉雅自动发布 POC

State: **code + offline tests done (PR #43); waiting for Leon's WeChat scan to run on the real site.** Not in a release batch; the App is untouched.

Details, safety rules and the run commands: `spikes/s6_ximalaya/README.md`.

## Progress
- 2026-10-17: open platform checked, no upload API for personal creators. Playwright script `xmly.py` (login / probe / draft / publish-private), `draft` stops before 确认发布 with 权限=私密. Tests `tests/test_s6_ximalaya.py`.
- Next: after phase 7's migration of Leon's PC, coordinator gives the go; Leon scans the WeChat QR once; run `probe` + `draft` with `--capture`; record results in the spike README; ask Leon before any `publish-private`.
