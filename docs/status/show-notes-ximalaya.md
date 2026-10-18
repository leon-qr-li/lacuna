# Show notes 喜马拉雅版 (backlog item 26)

State (2026-10-18): built, tests green, waiting for the batched release and Leon's test in the real
喜马拉雅 editor. Decision: docs/decisions/2026-10-18-ximalaya-show-notes.md.

- No tables anywhere (prompt, example, renderer, `untable` on save/open, web Markdown renderer).
- Tab 「发布 → 喜马拉雅版」: 杂志 / 片场 / 图文, copy rich + plain, images for 图文 with download.
- POC from Leon's real EP001 notes (BGM lines are sample credits from his library, for layout only):
  /mnt/project-files/lacuna/show_notes/ximalaya_poc/ (each layout as .html with a copy button + .txt,
  banner.png, films.png). The POC images were drawn with WenQuanYi; the app uses 微软雅黑.
- Tests: tests/app/test_ximalaya.py, tests/app/test_publish.py (no-table cases), web/e2e/ximalaya.spec.ts.

Next: Leon picks a layout after pasting into 喜马拉雅; then remove or keep the others.
