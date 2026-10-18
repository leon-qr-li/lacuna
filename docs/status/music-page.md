# Music page improvements (首次检测 15, 16, 17, 18, 19, 21, 22)

State: merged (PR #93), waiting for Leon's validation in the 2026-10-18 batch
(steps: /mnt/project-files/lacuna/docs/验收_2026-10-18/01_配乐页.md).

- Backend: `lacuna_app/music.py` (auto / loop beds in `layout` → `_fill_beds`; `loop_passes`;
  `transitions` + `listen_s`; role change in `update`; BG_DB 22), `lacuna_app/routes/music.py`
  (`auto` / `loop` fields; a new interlude / clip goes to a pause).
- Web: `web/src/features/library/MusicView.tsx` (picker label, type picker, bed options, one player
  with strip playhead, ±5 s), `library.css`, `en.ts`, `api.ts` types.
- Tests: `tests/app/test_music_page.py`, `web/e2e/music_page.spec.ts` (+ label updates in
  `music.spec.ts`, which now finds rows by `data-role`).
- Decision: `docs/decisions/2026-10-18-bed-auto-loop.md`.
- Music level (items 7, 20) is the levels feature's (`levels.music_level_db`, PRs #94 / #96): see `levels.md`.
