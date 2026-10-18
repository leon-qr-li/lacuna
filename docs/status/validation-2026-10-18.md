# 验收 2026-10-18 — fixes from Leon's validation

Issues Leon raised while validating v2026.10.18.2/.3; tracked in
`/mnt/project-files/lacuna/docs/验收_2026-10-18/10_验收中发现的问题.md`.

| # | Issue | State |
|---|-------|-------|
| V1 | Top bar: on 素材库 / 学到的规则 / 设置 the page's own link vanished; only 剧集 stayed and highlighted | Fixed: every top-bar link stays on its page, selected (`navCurrent` in `features/registry.ts`) |
| V2 | An approved rule that gained new examples asked to be adopted again | Fixed: same rule id stays approved, snapshot refreshed (`Learning.overview`); only brand-new rules wait for Leon. Decision `docs/decisions/2026-10-18-approved-rules-stay-approved.md` |
| V3 | 导入任务 card still said "31 处需要你过目" after the episode was fully reviewed | Fixed: card shows the episode's live pending count and goes away at 0 |
| V4 | Import progress: per-step minutes ("20/40 分钟") don't match the overall ETA | Open: show one overall time left, steps as percentages |

Tests: `tests/app/test_learning.py`, `web/e2e/episodes_nav.spec.ts`, `web/e2e/import.spec.ts`.
