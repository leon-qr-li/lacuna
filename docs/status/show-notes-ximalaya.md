# Show notes 喜马拉雅版 (backlog item 26)

State (2026-10-18): merged (PR #89), waiting for Leon's validation in the 2026-10-18 batch and his test in
the real 喜马拉雅 editor (steps: /mnt/project-files/lacuna/docs/验收_2026-10-18/08_show_notes.md). Item 27 is merged into 26. Decision: docs/decisions/2026-10-18-ximalaya-show-notes.md.

- No tables anywhere (prompt, example, renderer, `untable` on save/open, web Markdown renderer).
- Tab 「发布 → 喜马拉雅版」: 杂志 / 片场 / 图文, copy rich + plain, images for 图文 with download.
- POC from Leon's real EP001 notes (BGM lines are sample credits from his library, for layout only):
  /mnt/project-files/lacuna/show_notes/ximalaya_poc/ (each layout as .html with a copy button + .txt,
  banner.png, films.png). The POC images were drawn with WenQuanYi; the app uses the system font (微软雅黑 on Windows, 苹方 on macOS).
- Tests: tests/app/test_ximalaya.py, tests/app/test_publish.py (no-table cases), web/e2e/ximalaya.spec.ts.

2026-10-18 (V9): Leon picked 「片场」. It is now the default and starts at the title (no "<episode> · 洛城二三事" line);
decision docs/decisions/2026-10-18-ximalaya-cinema-default.md. Waiting for the batched update + validation.
