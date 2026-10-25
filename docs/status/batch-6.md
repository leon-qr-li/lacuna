# Batch 6: terms + privacy, patrol and support design, storage stress test

Thread 「第六批:条款与巡检客服」, branch `claude/project-thread-9e2dfv`, one integration PR. Leon said 「做」 on
2026-10-25 04:19Z to the coordinator's proposal: (1) build the ToS + privacy draft with the sign-up tick, (2) DESIGN
ONLY the admin patrol + daily digest and the in-app 「LACUNA 客服」, (3) stress-test the cloud audio storage.

## Done (code + tests)
- 用户条款 / 隐私政策 draft, zh + en, at `/legal/terms` and `/legal/privacy`; tick to agree at sign-up (first
  account and invites); accounts without the current version agree once after signing in (cloud). Decision
  `2026-10-25-terms-and-privacy`. Code: `lacuna_app/legal.py`, `lacuna_app/routes/legal.py`, `auth.py` (register
  records it, status reports it), `web/src/features/legal/`, `AuthScreen.tsx`, `AuthGate.tsx`, `AccountCard.tsx`.
  Tests: `tests/app/test_legal.py`, `web/e2e/legal.spec.ts`; sign-up specs tick the box.

## Open
- Placeholders in the documents (entity, law, DMCA agent, emails…): fill with the lawyer before public launch.
- Patrol / digest and 「LACUNA 客服」: design proposals for Leon; no code until he says build.
- Storage stress test: see below when run.
