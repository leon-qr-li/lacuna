# Phase 8 — UI 审美（大改版）

State: **done — accepted by Leon 2026-10-17 17:11Z** (rounds 1 + 2 on his PC)

What Leon gets: a modern, calmer UI ("C 轻盈"): a clear 5-step flow per episode, buttons next to the work they do,
bundled fonts that look right on his PC, and a dark / light theme. Functions and logic do not change.
Decision: `docs/decisions/2026-10-17-ui-redesign-c-focus.md`.

## Progress
- 2026-10-17 15:51Z round 1 mockups (A / B / C / D) → Leon picked C. 16:00Z round 2 (every page, light / dark /
  English) → Leon: "先按这版本改，待会儿再 iterate".
- PR #48: fonts bundled (Inter + MiSans VF + JetBrains Mono, no Google Fonts), token-based light / dark theme
  (`web/src/features/theme/`, toggle in the top bar, remembered, follows the OS by default), base styles restyled;
  E2E `web/e2e/theme.spec.ts`.
- PR #50: shell. Top bar = crumb + 素材库 / 学到的规则 / 设置 / theme (+ 「AI 制作人」 toggle in 整集试听).
  Under the title: status chip, ghost 撤销 / 重做, primary 导出. Step pill 审阅改动 → 整集试听 → 配乐 → 导出 → 发布;
  tabs can declare `group` (registry) and grouped tabs become one step with sub-tabs (发布 = 发布资料 / 海报 /
  上传喜马拉雅). 导出 is its own step (`features/export`, ExportPanel `inline`). Each step ends with 「下一步：…」.
  设置 → 外观 (浅色 / 深色 / 跟随系统; language row, English disabled until i18n).
- PR #51: 审阅改动 floating dock (prev / A·B pill / 恢复原话 R / 保留这个删除 Y / next), cleaner detail cards;
  配乐 header with 按用途自动放好, whole-episode music strip (click a block to hear it), tuning box per placement.
- PR 4: home hero + episode cards with a cover tile and status chip; 设置 link on every screen; 上传喜马拉雅 step
  numbers.

## Next
- Batch update (coordinator), then Leon validates and we iterate on colours / spacing / layout.
- Then the i18n thread resumes (labels already flexible; English mockups checked in round 2).

## Coordination
- 6a thread no longer touches App.tsx, the review player, MusicView or ExportPanel (done with #47 / #49).

## Round 2 (Leon's feedback after the 2026-10-17.3 update)
- Episode cards equal height; AI 制作人 wider (460px) and fills the right column even with no conversation;
  text boxes are multi-line and grow (`components/GrowText.tsx`: Enter sends, Shift+Enter new line) in the chat,
  review tweak, music chat, library note and poster revise; inputs 15px; the 放一段音乐 picker shows a short label
  (long credits trimmed) and never overflows. E2E `web/e2e/layout.spec.ts`.
