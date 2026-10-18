# 验收 2026-10-18 — fixes from Leon's validation

Issues Leon raised while validating v2026.10.18.2/.3; tracked in
`/mnt/project-files/lacuna/docs/验收_2026-10-18/10_验收中发现的问题.md`.

| # | Issue | State |
|---|-------|-------|
| V1 | Top bar: on 素材库 / 学到的规则 / 设置 the page's own link vanished; only 剧集 stayed and highlighted | Fixed: every top-bar link stays on its page, selected (`navCurrent` in `features/registry.ts`) |
| V2 | An approved rule that gained new examples asked to be adopted again | Fixed: same rule id stays approved, snapshot refreshed (`Learning.overview`); only brand-new rules wait for Leon. Decision `docs/decisions/2026-10-18-approved-rules-stay-approved.md` |
| V3 | 导入任务 card still said "31 处需要你过目" after the episode was fully reviewed | Fixed: card shows the episode's live pending count and goes away at 0 |
| V4 | Import progress: per-step minutes ("20/40 分钟") don't match the overall ETA | Won't change: Leon read 40 min as the audio length, the display is right |
| V5 | Single-track erase played the host's own words from the track's first minute, looped | Root cause: before .3 `room_tone.pick` returned a window offset, not a track position (fixed in #103 for new erases). Episodes imported before .3 keep those tones, so opening an episode now re-picks any tone outside the search window and saves it (`room_tone.misplaced`, `Episode.__init__`). Leon's re-imported `test` episode had 93 of 95 tones misplaced |

Tests: `tests/app/test_full_scan_audio.py`, `tests/app/test_learning.py`, `web/e2e/episodes_nav.spec.ts`, `web/e2e/import.spec.ts`.
