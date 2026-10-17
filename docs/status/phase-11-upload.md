# Phase 11 — 上传喜马拉雅（辅助发布）

State: **built, merged into the next batch; waiting for the batch update + Leon's validation**

What Leon gets: one page with everything for the 喜马拉雅 upload form, in its order — download the WAV, copy the
title, copy the show notes (rich text), download the cover — and what is still missing or out of date. Leon uploads
by hand: 喜马拉雅 has no upload API for personal creators and Leon dropped browser automation
(`docs/decisions/2026-10-17-ximalaya-no-upload-api.md`).

Depends on: 9, 10 · Uses the export (D36)

## Progress
- 2026-10-17: open platform checked (no creator upload API); Leon chose manual upload from a ready page. Page built.

## How it is built
- UI: episode tab 「上传喜马拉雅」 (`#/ep/<id>/upload`, `web/src/features/upload/`): summary (all ready / what is missing /
  what is stale) + link to studio.ximalaya.com; 1 音频 (newest WAV, download, open folder; stale if exported from an
  older cut), 2 标题 (copy), 3 简介 (show notes rich copy + one-line blurb; stale timestamps → 发布资料 「更新时间戳」),
  4 封面 (preview + download as `<episode>_cover.jpg`); missing items link to the tab that makes them.
- API: `GET /api/episodes/{id}/upload` (checklist), `GET …/upload/cover.jpg` (attachment). WAV downloads through the
  existing `…/exports/{name}`. Logic in `lacuna_app/upload.py`; nothing new is generated, no Claude calls.
- Tests: `tests/app/test_upload.py`, `web/e2e/upload.spec.ts`.
- Not done (from the roadmap line): checking that the episode actually went live on 喜马拉雅 / 小宇宙.
