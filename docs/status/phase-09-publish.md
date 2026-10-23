# Phase 9 — 发布资料包

State: **done, validated by Leon 2026-10-17** (D46)

What Leon gets: 标题（可换候选）、一句话简介、show notes（D40 样式）、成品时间线上的章节、专有名词核对，一键复制（富文本 + Markdown）

Depends on: 2 · Parallel with: 6a

## Progress
- **Phase 9 publish pack built** (2026-10-17, D46): episode page 「发布资料」 → Claude writes title / blurb / show notes from the current cut's transcript (text only), timeline times computed locally on the final cut, Markdown in the D40 format, copy = rich text + Markdown, chapters, name check (corrections remembered in `names.json`), local re-timing after later edits. BGM from the 6a library once it lands (placeholder until then). Validated by Leon 2026-10-17 on EP001_AI with the real Claude ("我很喜欢这个 show note").

## How it is built (发布资料包 (2026-10-17, D46))
- UI: step 发布 → 「发布资料」 (`#/ep/<id>/publish`; a top-bar tab before phase 8): 生成发布资料 → title (alternatives one click away), one-line blurb, show notes preview (Markdown in the D40 format) with 复制（带格式）= rich HTML + Markdown on the clipboard at once, 复制 Markdown, 编辑 (Leon's Markdown is kept), chapters (copy as `mm:ss 标题` lines), 专有名词核对 (改成 X / 不用改). After a later cut change: banner 「更新时间戳」 (local, free; hand edits kept, only bold timestamps swap); entries whose audio was cut later are listed.
- API: `GET /api/episodes/{id}/publish`, `POST …/publish/generate` (background job), `POST …/publish/retime`, `PUT …/publish {markdown?|null, title?}`, `POST …/publish/names {heard, action: apply|ignore}`.
- Engine `lacuna_app/publish.py`: transcript of the current cut (`Episode.utterances`, cuts/lifts/slips applied) → numbered segments anchored in base time → one streamed Claude request (`claude-opus-5-5`, effort `LACUNA_PUBLISH_EFFORT`, default medium; strict tool `submit_publish_pack`; brief `prompts/show_notes_brief.txt` + approved example `prompts/show_notes_example.md`) → entries cite segment ids, times computed locally → Markdown rendered locally. Without a key: a time-sliced skeleton, labelled.
- Music (6a): `music_info` builds the `lacuna_app.music` layout once per call (same data as `music.bgm_credits` / `music.final_time`: credit lines, final-timeline positions, voice → final shift from inserted intro/interludes); 片头/间奏/片尾 lines join the timeline, the BGM section lists the credits ("BGM：未设置" when none).
- Files: `<episode>/publish.json` (schema 1, via `store`), `<workspace>/exports/<episode>/publish/notes.md` (rewritten on every save), `<workspace>/names.json` (names Leon corrected; applied to the next transcript and listed in the prompt). Cost logged to `ai_usage.jsonl` (`kind: publish`).
- Real-key check: `scripts/publish_smoke.py --workspace … --episode …`.
- Tests: `tests/app/test_publish.py` (fake client), `web/e2e/publish.spec.ts`.

## Later changes
- 2026-10-18 (backlog 26, #89): show notes never contain tables (prompt, example, renderer, `publish.untable` on save/open) and a 「喜马拉雅版」 sub-tab with three layouts: `show-notes-ximalaya.md`.
- Interface text calls the writer LACUNA / AI, not the vendor (`dialog-brand.md`); 重新生成 / 恢复成生成的版本 confirm through the in-app dialog.
- 2026-10-23 (decision `show-notes-detail-levels`): 精简 / 标准 / 详细 switch on the Show notes card. The brief asks the writer to rank every entry (tool field `rank` 1–3); `publish.thin` filters the timed rows per level (`LEVELS`, min gap on the final cut, a part's first line always kept); `pack.level` (new packs `std`, old ones `full`), `pack.counts` per level and `pack.duration` in the view; `PUT …/publish/level {level, rev}`. Tests `tests/app/test_publish_levels.py` + the end of `web/e2e/publish.spec.ts`.

## 自动发布 即将推出 (2026-10-23)
- Decision `2026-10-23-auto-publish-coming-soon`: direct publishing after beta; LACUNA never hosts or serves RSS.
- Built: 节目设置 → 发布 「自动发布」 section (web/src/features/show/ShowForm.tsx): 即将推出 + Apple Podcasts /
  Spotify / YouTube / Amazon Music checkboxes + 「告诉我们」 (no target yet). Saved as `publish.auto_wish`
  (lacuna_app/show.py `AUTO_PUBLISH`; PUT /api/show keeps it when left out). Tests: tests/app/test_show.py,
  web/e2e/auto_publish.spec.ts.
- Next: point 「告诉我们」 at the feedback page; show the counts in the admin batch; after beta, the five questions in
  the research doc.
