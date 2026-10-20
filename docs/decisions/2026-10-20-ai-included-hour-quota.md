# AI is included in the subscription price, limited by a monthly allowance of audio hours

- Date: 2026-10-20
- Status: CONFIRMED（Leon 2026-10-20 07:16Z：「B，这个记一下，将来也要做，在上线之前做，这是一个大方案，必须做」）
- Supersedes / changes: refines D23 (who pays for runtime AI once other people use the app)

Users never buy an AI plan or bring their own key. The subscription includes all AI features; each plan
gives a monthly allowance of audio hours that LACUNA processes (working numbers: Creator US$29 / 4 h,
Pro US$59 / 12 h). When the allowance is used up the app says so and the user waits for next month or
upgrades. A paid top-up pack ("+2 hours", about US$5) is the planned add-on once payments exist
(option C), not part of this decision.

Why: users of an AI-native tool expect one price with AI included (option D, bring-your-own-key, was
rejected); an unlimited plan (option A) has no cost ceiling. Measured cost: AI first cut of a 73.5-minute
episode on Sonnet 5.5 = $2.12; a 1-hour episode costs about $3.3 in AI today (first cut + ~30 chat edits
+ publish pack + poster/lessons), about $1.8 after the planned savings (Batch API for the first cut, chat
on Sonnet 5.5, Haiku 5.5 for small jobs, prompt caching). Hours are the unit because users understand
them and cost scales with them.

Compliance: the server calls the Messages API with an API key from Leon's Console organization (never a
claude.ai subscription login). The Commercial Terms (A.1) allow using the Services "to power products and
services Customer makes available to its own customers and end users"; the Max-included API credits are
only barred from being transferred or sold (Credit Terms B.2). When the company exists the Console
organization moves to it; no code change.

Must ship before public launch (`docs/status/beta-launch-todo.md`):
- per-workspace monthly audio-hour allowance, enforced at import, with a usage display
  ("本月已用 1.5 / 4 小时") and a clear message when it runs out;
- an AI spend limit set on the Console organization as a second guard;
- the cost savings above, each checked for quality before switching.

Analysis: `/mnt/project-files/lacuna/docs/AI费用与收费方案_2026-10-20.md`; business model recomputed
under this option: `/mnt/project-files/lacuna/docs/商业粗算_方案B_2026-10-20.md`.
