# Audio hours are metered at import, with every rule an admin setting until the business model is decided

- Date: 2026-10-24
- Status: CONFIRMED（Leon 2026-10-25「全部同意，都按着你的推荐」，第五批问题 4）
- Supersedes / changes: builds on `2026-10-20-ai-included-hour-quota`

`lacuna_app/quota.py`. An import counts when it succeeds (its first cut is made), for the episode's length (the
longest track); failed or cancelled imports cost nothing, resuming costs nothing extra, and the same files imported
again in the same month count once. Hours go against the account that made the show (collaborators spend the
creator's). Allowance a month = plan hours (the trial's 1 hour is once, ever) + hours the owner approved this
month + 1 hour per adopted feedback this month. An import may start while any hours are left, so the last episode
may go over; with none left it is refused and points to 「想要更多时长」. The owner's and admins' own shows are counted
but never refused. A month is a UTC calendar month. Every rule (enforce, must_fit, staff_exempt, repeat_free) is
a switch in the admin (时长申请 → 套餐与 beta → 计量规则), so the business-model decision needs no release.
设置 → 套餐与用量 shows hours used of this month's allowance; the admin's users and 时长申请 pages show real usage.
