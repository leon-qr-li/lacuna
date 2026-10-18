# The AI is called LACUNA in everything users see

**Date:** 2026-10-18 · **Asked by:** Leon (首次检测 backlog item 28)

Leon does not want users to know which model or company is behind the AI. Anything a user sees
(interface text in Chinese and English, AI replies, error messages, settings) never says Claude,
Claude Code or Anthropic.

- The AI is "LACUNA" ("让 LACUNA 查正式曲名", "LACUNA 在想…", the chat badge "LACUNA").
- When the point is the cloud call itself (privacy notes, network errors), the text says "云端 AI" /
  "AI 服务" ("only text and numbers go to LACUNA's cloud AI", "连不上 AI 服务（网络问题）"), so it
  stays honest that text leaves the machine without naming the vendor.
- No key / no SDK: "还没接上 AI（没有 AI 密钥）". The settings card is "AI 密钥" / "AI key"; the
  placeholder no longer shows the vendor's key prefix. Leon knows which key goes there.
- Prompts whose output Leon reads end with `i18n.AI_NAME_RULE` ("you are LACUNA; never call
  yourself Claude, never mention Anthropic"). Music credits may still name people called Claude
  (Debussy): the rule is about the AI's self-reference, not a text filter.
- Internal code, identifiers, the `"claude"` editor id, env var `ANTHROPIC_API_KEY`, API calls and
  engineering docs are unchanged.

**Checks:** `web/scripts/brand-check.mjs` (part of `npm run build`: no string or JSX text in web/src
contains Claude / Anthropic / sk-ant), `tests/test_brand_text.py` (server tr()/N_() keys + English,
prompt rule), `web/e2e/brand_text.spec.ts` (every screen in zh + en, visible text and
title/placeholder/aria-label, with and without the AI connected).
