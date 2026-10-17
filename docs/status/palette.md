# UI palette → logo colors

- 2026-10-17: three palettes shown (screenshots/palette/), building B 夜航 while Leon picks. Decision: docs/decisions/2026-10-17-palette-logo.md.
- Implementation: token swap in web/src/styles.css + violet shadows in auth.css / library.css → `--glow`; login art panel uses sunset glows. Test: web/e2e/palette.spec.ts (logo colors + WCAG AA contrast, light and dark); theme.spec.ts background value updated.
- Mockup tooling: screenshots/palette/mockups/ (inject a variant CSS into the running E2E app and screenshot).
- Leon picked B 20:47Z; PR #76. Next: batch update, then validation.
