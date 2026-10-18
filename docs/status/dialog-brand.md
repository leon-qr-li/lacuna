# Global dialog + brand text (首次检测 items 13, 14, 28)

## #28 no vendor name in the interface — in review
- All user-visible Claude / Anthropic text replaced (web t() keys + en.ts, server tr()/N_() + i18n_en.py,
  settings "AI 密钥", chat badge/usage "LACUNA", prompts end with `AI_NAME_RULE`).
- Decision: `docs/decisions/2026-10-18-ai-called-lacuna.md`.
- Checks: `web/scripts/brand-check.mjs` (in `npm run build`), `tests/test_brand_text.py`,
  `web/e2e/brand_text.spec.ts`.

## #13 in-app confirm dialog — todo
## #14 concurrent title lookups in the media library — todo
