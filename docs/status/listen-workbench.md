# 整集试听 workbench (thread 整集试听页面布局)

Decision: `docs/decisions/2026-10-20-listen-workbench.md`.

## Where the code is
- `web/src/features/workbench/` — `Workbench.tsx` (SideTabs, Minimap, CutPop, NextStep), `workbench.css`, `en.ts`.
- Small hooks in shared code: `EditLanes` takes `top` / `bottom` / `popover`; `ChatPanel` takes `tabs` / `alt`;
  `NearbyEdits` exports `nearEdits`; `ChatCollapse` wraps its label (hidden in English inside the tabs);
  `App.tsx` lays out 整集试听 and puts 下一步 in the header row.
- Tests: `web/e2e/workbench.spec.ts`; nearby-list checks in `app` / `claude` / `manual` specs open the tab first;
  timeline marks carry `data-title` (the native `title` tooltip is off where the card opens).

## State
- 2026-10-20: built, local E2E 109/109; PR to staging when the queue frees, then Leon's 通过.

## Next
- Ideas not built: keyboard keys for the tabs; draggable split between timeline and transcript.
