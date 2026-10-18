# Phase 4 — 新一集导入

State: **done**, validated by Leon 2026-10-17 (D41, D44)

What Leon gets: 在 App 里选两条分轨（拖进来或选择文件）→ 后台跑 ASR、分析、AI 第一刀，任务面板显示进度和剩余时间，两人音量自动拉平，完成后直接进入审阅

Depends on: 3 (first cut runs through the API at runtime) · Parallel with: 5

## Progress
- **Phase 4 new-episode import** (2026-10-17, D41): Home → 导入新一集 → pick Leon/Pei tracks → local ASR (Paraformer + SenseVoice, sherpa-onnx) → features → Claude first cut in ~10-min windows → review. Resumable per step (`<workspace>/imports/<id>/`). Real ASR verified on sherpa test clips in the cloud box; full EP001 run on Leon's PC pending (needs `pip install -e ".[asr]"`, first import downloads ~400 MB of models).
  - 2026-10-17 first real run on Leon's PC (EP001 raw, 73.5 min): models download ~30 s, ASR Leon 268 s + Pei 197 s, features ~20 s, peak RAM ~1.5 GB. Claude step refused on Opus (D44) → first cut now Sonnet 5.5. After the batch update (main aae392a) the job resumed: Sonnet 5.5, 8 windows, 0 refusals, 8 min 50 s, $2.12; 273 ops → 272 edits, 64 to review (EP001_AI had 646). **Validated by Leon 2026-10-17** ("导入的功能过了").

## How it is built (新一集导入 (2026-10-17, D41))
- UI: Home → 「导入新一集」: episode id (next free EPnnn), optional title, Leon's / Pei's track picked in a local folder browser (`GET /api/fs`; Pei's file is guessed from the same folder) — replaced 2026-10-18 by drag & drop / 「选择文件」 (#4 below; `GET /api/fs` stays, unused by the UI). Task panel under it: stage, progress bar, elapsed, 取消 / 继续 / 开始审阅 / 从列表移除; a job that finishes while Home is open opens its review.
- API: `POST /api/imports {id, title, leon, pei}`, `GET /api/imports` (+ `next_id`), `GET /api/imports/{id}`, `POST …/resume`, `POST …/cancel`, `DELETE …`.
- Pipeline (`lacuna_app/importer.py`): models (first time, ~400 MB from the sherpa-onnx GitHub releases into `<workspace>/models`) → ASR per track (`asr.py`) → features + editor document (`features.py`) → AI first cut (`first_cut.py`, windows of ~10 min, cached per window) → episode (`ai_cut.build_episode`) → host levels evened out (`importer._level` → `levels.level_new_episode`, one `track_gain` edit per track, no undo step; a failure only skips it; see `levels.md`). Cache: `<workspace>/imports/<id>/` (asr_L/P.json, tokens/features.json, editor_input.md, ai_windows/, ops.json, job.json).
- Needs `pip install -e ".[asr]"` (sherpa-onnx) and ffmpeg. Without a key the first cut is rules-only (pause targets), labelled as such.
- Tests: `tests/app/test_import.py` (fake ASR + fake Claude, real decoding/features/conversion/episode), `tests/test_asr_real.py` (real models; set `LACUNA_ASR_MODELS`), `web/e2e/import.spec.ts`.

## 首检 follow-ups (2026-10-18, items 2–5)
- #2 Signing in (or creating the account) always lands on 剧集 (`features/auth/AuthGate.tsx`); it used to stay on 设置 where the sign-out happened.
- #3 Archive (decision `archive-delete-keeps-learning`): 归档 on each tile with an 撤销 toast; 「已归档 · n」 under the list opens `#/archive` with 恢复 / 永久删除. Code: `lacuna_app/archive.py`, `routes/archive.py`, `web/src/features/episodes/` (Home moved out of App.tsx into `Home.tsx`); 永久删除 asks through the shared `features/dialog` confirmDialog. Tests: `tests/app/test_archive.py`, `web/e2e/archive.spec.ts`, last test of `web/e2e/import.spec.ts`.
- #4 Drag & drop import (decision `import-drop-and-eta`): `web/src/features/import/` (ImportPanel moved there), `lacuna_app/import_tracks.py`, `POST /api/imports/tracks`, `POST /api/imports/tracks/remove`. Tests: `tests/app/test_import_tracks.py`, `web/e2e/import.spec.ts`.
- #5 Time left: `lacuna_app/import_eta.py`, `eta_s` in the running job; `JobProgress` takes the server's `left`. Tests: `tests/app/test_import_eta.py`.

