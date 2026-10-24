# 用户反馈: the user side in the app, everything kept for the admin

Date: 2026-10-24. Decided by Leon (thread 设计用户反馈功能; proposal doc https://claude.ai/artifact/Gk7gdbRMtpAYWmeN5XKe4o,
UX canvas https://claude.ai/artifact/6BNFqokSF4evJqPMiBH7bS). Leon: 「做，按照你的推荐」.

## Decision
- This batch is the user side only. Everything people send goes to our own server for the admin back office
  (its own batch, designed by Leon, done before beta). How the site owner reads, answers and approves is not
  designed here; until the admin exists the owner-only API (`/api/feedback/all`, `/api/feedback/{id}/reply`) is it.
- Entry: a 反馈 button in the top bar on every screen (Q1 A). It opens a side panel: 遇到问题 / 我有个想法 / 夸一句,
  text or voice input, and for 遇到问题 a screenshot of the LACUNA page taken when the panel opens, on by default and
  removable, replaceable and markable (Q2 A). Attached by itself: the page, the episode and playhead, app version,
  browser, interface language, the last 20 steps (pages opened, changes sent, failures) and the latest error.
- 「告诉我们」 sits next to export and import errors and opens the panel filled in with the error. The 自动发布 card's
  「告诉我们」 (decision 2026-10-23-auto-publish-coming-soon) opens it as an idea with the platforms ticked.
- One question at key moments, at most once in 7 days per person, never during editing, 不再问我 stops it (Q3 A):
  a rating plus time saved after the first exported episode, the 「如果从明天起用不了 LACUNA」 question after the third.
  The sample show doesn't count.
- A new show's first setup asks two optional questions: where the host and listeners are, and how they edit now
  (Q4 A). The show's language is the setup's own field, so it is not asked again; the admin sees it with the answers.
- 我的反馈 (in the panel, and at `#/feedback`, the reply email's link) lists what the person sent, its status (已收到 →
  在处理 / 在计划中 → 已修好 / 已上线, or 暂不做) and the owner's replies. A reply shows a red dot on 反馈 until looked at
  and sends an email in the person's language (Q5 A).
- 采纳送 1 小时: an adopted item records 1 bonus hour for that month; it counts once hour quotas exist (batch 5).
- 夸一句 asks for leave to quote it publicly, signed with the show's name only (unticked by default).
- Feedback, screenshots and answers never go to the AI, the event log or the code repository. Deleting an account
  deletes its feedback and screenshots.
- Until the admin back office existed, there was no owner page: Leon told Claude, and Claude answered on the server
  with a script (reply, status, 采纳, reset the one-question prompts). Leon picked this over a temporary page
  (2026-10-24). Superseded the same day by the admin site's 反馈 page (decision 2026-10-24-admin-site); the script
  is deleted.
- Not in this batch, decided before beta with the business model: extra hours, paying in beta, the beta's length.

## Where
`lacuna_app/feedback.py`, `lacuna_app/routes/feedback.py` (tables `feedback`, `feedback_profiles` in the site database;
screenshots in `<root>/feedback/`), `web/src/features/feedback/`, tests `tests/app/test_feedback.py`,
`web/e2e/feedback.spec.ts`.
