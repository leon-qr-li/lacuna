# Global dialog + brand text (首次检测 items 13, 14, 28)

## #28 no vendor name in the interface — in review
- All user-visible Claude / Anthropic text replaced (web t() keys + en.ts, server tr()/N_() + i18n_en.py,
  settings "AI 密钥", chat badge/usage "LACUNA", prompts end with `AI_NAME_RULE`).
- Decision: `docs/decisions/2026-10-18-ai-called-lacuna.md`.
- Checks: `web/scripts/brand-check.mjs` (in `npm run build`), `tests/test_brand_text.py`,
  `web/e2e/brand_text.spec.ts`.

## #13 in-app confirm dialog — in review
- `web/src/features/dialog/`: `confirmDialog({message, title?, confirmLabel?, danger?})` → Promise<boolean>,
  `noticeDialog(message)`; renders into its own root on <body> (no screen mounts anything). Esc /
  取消 / backdrop cancel, Enter confirms, focus starts on the confirm button and stays inside, keyboard
  shortcuts underneath are blocked while it is open. Danger = true red (#d42a45 in dark for white text).
- Replaced all 4 native calls: 移出素材库 (danger), 重新生成 show notes (danger when hand-edited),
  恢复成生成的版本 (danger), 再画 N 版海报.
- `web/scripts/brand-check.mjs` now also fails the build on any confirm() / alert() / prompt() call.
- Test: `web/e2e/dialog.spec.ts` (light + dark: red button, contrast ≥ 4.5, Esc / 取消 / backdrop keep,
  Enter removes, no native dialog; English labels).

## #14 concurrent title lookups in the media library — in review
- Cause: each row's result was applied to the list as it was when its button was clicked, so the
  lookup that finished last put the earlier one's row back (its result vanished). `replace` now uses a
  functional state update. Server side was already safe (one Library, RLock).
- Test: `web/e2e/library_lookup.spec.ts` with `tests/app/fake_credit.py` (overlapping fake lookups,
  notes "并发 A 慢" / "并发 B"); it fails on the old code.
