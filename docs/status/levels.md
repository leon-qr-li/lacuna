# Voice + music levels (backlog 7, 20) - 2026-10-18

State: merged (#94 + follow-up), waiting for the next batched release.

- `lacuna_app/levels.py`: measure host tracks (cached in `<episode>/levels.json`), plan even gains (−20 LUFS,
  peak-capped), gains as `track_gain` edits (one per track), chat volume parser, music loudness of the played range.
- Import (`importer.py` `_level`) levels a new episode right after it is built; a failure only skips it.
- API: `GET /api/episodes/{id}/levels`, `POST …/levels/{track}` (`gain_db` or `delta_db`), `POST …/levels/auto`.
  Chat: `routes/episodes.py` chat() answers volume requests before the AI editor.
- Web: `web/src/features/levels/` (tab 「声音」, order 15). Episode tabs can now replace the episode
  (`onEpisode` in `EpisodeTabProps`), so a gain change updates undo/redo and the main player.
- Music: `music.py` `_music_tracks` uses `EpisodeMusic.level_db` (played-range loudness); placements carry `level_db`.
- Tests: `tests/app/test_levels.py`, `web/e2e/levels.spec.ts`.
- 配乐 page shows each placement's automatic level under its numbers (`placement-level`, follow-up PR).
- Decision: docs/decisions/2026-10-18-loudness-leveling.md
