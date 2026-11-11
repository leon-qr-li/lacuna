# 用户动态 (admin)

Decision: docs/decisions/2026-10-31-admin-user-activity.md.

## State (2026-10-31)
- Server: `lacuna_app/admin_activity.py` (time window, show + episode names, audited looks), routes in
  `admin_api.py` (`GET /api/admin/users/{email}/activity?before=&days=`; the drawer's `activity` now has names);
  `routes/events.py` (failed changes, `events.note`, write in a worker thread), `exporter.py` (`export.done/error`).
- Web: `web/src/admin/activity/` (page, drawer summary, logic, demo data, en.ts, css); `/activity` is a hidden
  route in `Shell.tsx`; labels for every logged event in `labels.ts`.
- Privacy draft (zh + en) mentions the owner can view usage records.
- Tests: `tests/app/test_admin_activity.py`, `web/e2e/admin_activity.spec.ts`.

## Next
- Later (Leon picked "以后"): per-show activity; site-wide feed if there are many users.
