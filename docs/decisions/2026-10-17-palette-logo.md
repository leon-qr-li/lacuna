# UI palette follows the logo (V3 光晕)

**Context.** Phase 8 shipped a blue-violet accent (#5B6CFF) and a blue→violet→pink gradient. The new logo is a sunset line (amber → orange → pink → violet) on navy; Leon (2026-10-17 20:34Z) noticed the UI is mostly purple while the brand is orange-red.

**Options shown** (screenshots of the real app, light + dark: `/mnt/project-files/lacuna/screenshots/palette/`):
A 日落橙 (orange primary buttons, warm neutrals) · B 夜航 (logo navy for primary buttons and selected items, sunset only as highlight) · C 霓虹粉 (rose accent, keeps some violet).

**Decision.** B 夜航 (recommended; pending Leon's pick — switching is a token swap).
- Tokens only (`web/src/styles.css`): new `--primary` / `--on-primary` (navy #161B45 light, near-white dark) for primary buttons, current step, current review item, selected toggles, user chat bubble; `--grad` = the logo gradient; `--accent` orange; `--glow` replaces hard-coded violet shadows.
- Attention (`--warn`, 待过目 / struck text) moves to amber so it doesn't merge with the orange accent; `--danger` stays red.
- Pei's track color moves from peach to the logo's violet (peach would blur into orange cut marks); Leon stays blue.
- Every text/background token pair is ≥ 4.5:1 in both themes (`web/e2e/palette.spec.ts`).
