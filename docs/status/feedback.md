# 用户反馈 (feedback batch, started 2026-10-24)

Decision: `docs/decisions/2026-10-24-user-feedback.md`.

## State
- Built: 反馈 button + side panel (three kinds, voice input, screenshot with 换一张图 / 在图上圈出来, attached page details
  and last 20 steps), 「告诉我们」 on export / import errors and on the 自动发布 card, one-question prompts (rating after the
  first export, PMF after the third, ≤ 1 per 7 days, 不再问我), two optional questions in a new show's setup,
  我的反馈 with status, owner replies, red dot and reply email, `#/feedback` page.
- Owner side: API (`GET /api/feedback/all`, `POST /api/feedback/{id}/reply` with text / status / adopted,
  `GET /api/feedback/{id}/shot`, `POST /api/feedback/prompt/reset`) and, for Leon's 验收 before the admin exists,
  `scripts/feedback_admin.py` (list / show / reply / reset-prompts) that Claude runs inside the prod container
  (`docker exec <container> python scripts/feedback_admin.py …`); Leon chose this over a temporary page.
- Tests: `tests/app/test_feedback.py` (8), `web/e2e/feedback.spec.ts` (6).

## Notes
- The screenshot is drawn from the page (html-to-image), without web fonts (dozens of font files otherwise), as JPEG.
- The step trail wraps `window.fetch` in the feature (no core change): non-GET API calls and failed reads, page
  changes, script errors. Never bodies or typed text.
- The panel is mounted once on `<body>` (features/feedback/index.tsx), so it stays open across screens.
- Shown only when signed in (a checkout without accounts shows no 反馈).

## Next
- Leon's 验收 with his test account.
- Admin batch (replaces `scripts/feedback_admin.py`): list, reply, status, 采纳, screenshots, prompt answers and show profiles.
- Batch 5: count the adopted items' bonus hours in the monthly quota.
