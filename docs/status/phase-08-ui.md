# Phase 8 — UI 审美（大改版）

State: **in progress** — PR 1 (fonts + theme + base styles) open

What Leon gets: a modern, calmer UI ("C 轻盈"): a clear 5-step flow per episode, buttons next to the work they do,
bundled fonts that look right on his PC, and a dark / light theme. Functions and logic do not change.
Decision: `docs/decisions/2026-10-17-ui-redesign-c-focus.md`.

## Progress
- 2026-10-17 15:51Z round 1 mockups (A / B / C / D) → Leon picked C. 16:00Z round 2 (every page, light / dark /
  English) → Leon: "先按这版本改，待会儿再 iterate".
- PR 1: fonts bundled (Inter + MiSans VF + JetBrains Mono, no Google Fonts), token-based light / dark theme
  (`web/src/features/theme/`, toggle in the top bar, remembered, follows the OS by default), all base styles
  restyled; E2E `web/e2e/theme.spec.ts`.

## Plan (small PRs)
1. Foundation (this PR).
2. Shell: top bar, episode pipeline (with 导出 as a step, 发布 sub-tabs), floating dock, AI drawer; registry gets
   step metadata. Touches `App.tsx`, `features/registry.ts`, `PlayerBar`, `ChatPanel`.
3. Pages: review (after the 6a thread's 「带配乐听」 PR B), music + export panel (after PR #47), publish / poster /
   upload / library / rules / settings (appearance section with theme + language placeholder).

## Coordination
- 6a thread (素材库与配乐) owns MusicView / library and is adding a toggle to the review player: wait for its merges
  before touching those files (coordinator relays each merge).
- i18n thread paused until this lands; keep labels flexible (no fixed widths) — English mockups checked.

## Open
- Leon to iterate on colours / spacing after he sees it on his PC (batch update).
