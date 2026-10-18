# Review and editing fixes from the first full test (2026-10-18)

Backlog items 6, 8, 11 (`/mnt/project-files/lacuna/docs/UI_BACKLOG_首次检测.md`).

- 6 review speed: done. `web/src/features/review-speed/` (chip + `useReviewRate`), wired in `ReviewView` and
  `ABPlayer` (`rate` prop), key S in `review-keys`. Test `web/e2e/review_speed.spec.ts`.
- 11 previews 5 s either side: done (`Episode.ab`, `Previewer.around`). Tests `tests/app/test_api.py::test_edit_ab`,
  `web/e2e/review_speed.spec.ts`.
- 8 single-track erase with room tone: done. Core op `EraseRange` (`erase`) in `lacuna_core/edl.py`; tone picker
  `lacuna_app/room_tone.py`; the AI first cut's one-track cuts and the chat's `cut_one_track` now make erases;
  `create_episode` / `Episode.add_edit` pick the tone from the audio. Old episodes keep their plain lifts.
  Tests `tests/test_erase_room_tone.py`, `tests/app/test_erase.py`, `web/e2e/erase.spec.ts`.

Decisions: `docs/decisions/2026-10-18-review-speed-and-5s-context.md`, `docs/decisions/2026-10-18-erase-with-room-tone.md`.
