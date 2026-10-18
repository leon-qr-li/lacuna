# Library scopes (素材库：公共 / 本集)

Decision: `docs/decisions/2026-10-18-library-scopes.md`. Branch `v10-library-scopes` (local, not pushed).

## State (2026-10-18)
- Built: `lacuna_app/library.py` (scope fields + migration, `for_episode`, `move_to`, `make_shared`,
  `add_to_episode`, `drop_episode`), `routes/library.py` (`GET /api/library?episode=`, `episodes` list,
  upload `episode=`, `POST /api/library/assets/{id}/scope`), `routes/music.py` (add refuses another
  episode's asset), `music_assist.py` (auto / chat see shared + this episode), `archive.py` (permanent
  delete removes the episode's own assets). Web: `features/library/Scope.tsx` + `scope.css` (badge, actions,
  「加到」, filter, the 配乐 page's 「从电脑添加」), wired into `LibraryView.tsx` / `MusicView.tsx`.
- Tests: `tests/app/test_library_scopes.py` (9); `web/e2e/library_scopes.spec.ts` on a fourth E2E server
  (port 8796, default workspace + a second episode, `tests/app/e2e/library_scopes.py`, `LACUNA_E2E_SECOND_EPISODE`).
- Next: Leon validates in the batch release (add a file into an episode; the other episode's 配乐 page
  must not list it; delete an archived test episode and check its own files land in `library/_removed/`).
- Note: Playwright's `setInputFiles` did not fire a change event for the Chinese-named `洛城片头.wav`
  here; the spec drops that file instead (as `music.spec.ts` does).
