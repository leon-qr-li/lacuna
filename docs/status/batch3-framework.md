# Batch 3 「框架」 (2026-10-21)

Thread 第三批. Branch `claude/project-thread-hddmpe`, one integration PR, pre-launch flow (CI green → squash
merge → prod, no staging). Leon picked option A on all 11 questions of the decision pack (03:01Z).

## Built
- SQLite site database — decision `sqlite-site-data`; lacuna_app/db.py, auth.py, spaces.py. tests
  tests/app/test_site_db.py (+ auth/spaces tests updated to read the database).
- Plans — decision `plans`; lacuna_app/plans.py, routes/plans.py, web/src/features/plans (设置 → 套餐与用量),
  plan column/select in 设置 → 成员与邀请. tests test_plans_roles.py, e2e plans_roles.spec.ts.
- Roles + support access — decision `roles`; routes/spaces.py (`SETTINGS`, `may_manage`, `/support`),
  web/src/features/projects/ShowRoles.tsx. tests test_plans_roles.py, e2e plans_roles.spec.ts.
- Sign-in door — decision `app-sign-in`; turnstile.py, notice_mail.py, routes/auth.py, routes/auth_requests.py,
  cloud.py (`LACUNA_ACCESS=off`), web/src/features/auth (Turnstile.tsx, 申请试用 view), deploy/provision.py +
  deploy/site-door.txt. tests test_sign_in_door.py, test_cloud.py, tests/test_provision.py, e2e plans_roles/auth.
- Event log — decision `event-log`; events.py, routes/events.py. tests test_events.py.
- Polish (Leon 2026-10-21 04:24Z picks): invite form B 「分区表单」 (对方 / 节目 / 套餐) in
  web/src/features/auth/InviteForm.tsx + invite_form.css; 「已收到申请」 mail A 「夜航信笺」 to the person who asked
  (notice_mail.request_received, steps + no button; sent with the owner's notice, only for emails without an
  account). tests test_sign_in_door.py, e2e plans_roles.spec.ts.

## Not done here (on purpose)
- Cloudflare Access is still ON: deploy/site-door.txt says `access`. Opening it waits for Leon to type
  「关掉 Access」; then set `open`, merge, Provision `recreate` (token needs Account → Turnstile → Edit).
- Audio hour counting / enforcement: batch 5. The admin site (admin.<domain>): its own batch, design first.
- Trial sample episode content: the plan says it; the sample itself comes with the user tour (batch 4).

## Next
Leon validates on prod (steps in the thread). Then batch 4 / admin batch per the roadmap.
