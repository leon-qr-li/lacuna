# Admin site (admin.lacunastudio.app)

Decision: docs/decisions/2026-10-24-admin-site.md.

## State (2026-10-24)
- Built in one batch: 首页, 反馈 (inbox, reply + mail, 采纳, status, tags, notes, templates, 一题, 画像, NPS),
  时长申请, 邀请与申请, 用户 (drawer), 节目与剧集, 回收区, AI 用量与成本, 增长与留存, 系统健康, 系统设置, 操作日志;
  demo data, zh + en, light + dark, phone layout; daily digest and alert emails.
- Server: `lacuna_app/admin_host.py` (address split, Access check, headers), `admin_api.py` (routes, sign-in,
  step-up), `admin_store.py` (sessions, audit, notes, hour requests, error counts), `admin_metrics.py`,
  `admin_digest.py`; `routes/admin.py` (`register_last`), `routes/upkeep.py` (notice + maintenance),
  `routes/hour_requests.py` (想要更多时长).
- Web: `web/admin.html` + `web/src/admin/` (its own `t()`; dictionary `src/admin/en.ts`); main site:
  `features/site-notice/`, `features/plans/MoreHours.tsx`, NPS in `features/feedback/Prompts.tsx`.
- Deploy: provision adds admin.<domain> (tunnel route, DNS, Access app "LACUNA admin", owner only, 8 h) and
  `LACUNA_ADMIN_HOST` / `CF_ADMIN_ACCESS_AUD` to the real site's env (not staging). The env reaches the server only
  with `recreate` (Leon's typed OK).
- Tests: `tests/app/test_admin.py` (19), `tests/test_provision.py` (admin cases), `web/e2e/admin.spec.ts` (5).
- Local: open http://admin.localhost:8765 (staff with two-step sign-in only).

## Next
- Live after `provision apply` + `recreate`; Leon looks at it himself (no per-batch checklist; the full regression
  after code freeze is the acceptance).
- Then remove the main-site staff cards (成员与邀请 etc.).
- Before launch: passkeys.
