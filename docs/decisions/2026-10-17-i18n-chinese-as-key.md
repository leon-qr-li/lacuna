# Interface language: Chinese text is the translation key

Date: 2026-10-17 · Leon asked for a 中文 / English interface (analysis: `I18N_ANALYSIS.md` in the project files).

Decision
- UI text stays written in Chinese inside `t("中文")`; English lives in a per-feature `en.ts` (shell and shared
  components in `web/src/i18n/en.ts`). No i18n library: ~60 lines in `web/src/i18n/index.ts`.
- Plurals: an English entry may be `{ one, other }`, picked by the `n` parameter. Lists use `joinList`, dates `fmtDateTime`.
- The language is chosen in 设置 → 外观 (default 中文), stored in localStorage and the `lacuna_lang` cookie; switching
  reloads the page, so `t()` is a plain function (no React context) and works in module scope and helpers.
- `scripts/i18n-check.mjs` runs in `npm run build`: bare Chinese outside `t()` or a key without English fails the build.
  A line ending in `// i18n-ignore` is data, not UI text.
- Scope: interface only. The show stays Chinese: transcripts, show notes, titles, learned rules. AI meta-text (edit
  reasons, chat replies) follows the interface language (later PR).

Why
- Chinese as key keeps code readable for the Chinese-speaking owner, keeps every existing E2E selector valid (they
  run in Chinese), and makes the migration a line-local change that merges easily with parallel UI work.
- Per-feature `en.ts` follows the one-feature-one-folder rule in `PARALLEL_WORK.md`.
