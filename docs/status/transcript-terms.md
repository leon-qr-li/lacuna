# 文字稿按项目设置自动纠错 (decision `transcript-terms`)

Thread 文字稿按项目设置自动纠错 (2026-10-20). Leon: the transcript ignored the project settings
(洛城二三世, 利奥, 配, pose).

## Done (PR 1)
- `lacuna_app/transcript_fix.py`: glossary (show.json show name / hosts / `terms`, album names (albums.py),
  publish album, names.json, Latin words of the title), lines from ASR segments or an episode
  transcript, model call in chunks (4 in parallel), strict checks, word-text-only replacement.
- Import: `Importer._fix_terms` before `features.build`; the checked answer is cached in
  `imports/<id>/term_fixes.json`; raw `asr_*.json` stay as heard; step `terms` lists the fixes;
  usage logged as kind `transcript_fix`.
- Existing episodes: `POST /api/episodes/{id}/transcript/fix` + chip 「校对专有名词」 on 文字稿剪辑;
  `Episode.set_transcript` + summary `transcript_rev` so the transcript card reloads.
- Tests: `tests/app/test_transcript_fix.py`, `web/e2e/transcript_fix.spec.ts`.

## Next
- 项目设置: a 「专有名词 / Terms」 list (show.json `terms`, read already). Coordinate with the projects /
  albums thread (it is reshaping 项目设置).
- Maybe later: when Leon corrects a word by hand, remember it in names.json.
