# Review and editing fixes from the first full test (2026-10-18)

Backlog items 6, 8, 11 (`/mnt/project-files/lacuna/docs/UI_BACKLOG_首次检测.md`).

- 6 review speed: done. `web/src/features/review-speed/` (chip + `useReviewRate`), wired in `ReviewView` and
  `ABPlayer` (`rate` prop), key S in `review-keys`. Test `web/e2e/review_speed.spec.ts`.
- 11 previews 5 s either side: done (`Episode.ab`, `Previewer.around`). Tests `tests/app/test_api.py::test_edit_ab`,
  `web/e2e/review_speed.spec.ts`.
- 8 single-track erase with room tone: in progress.

Decisions: `docs/decisions/2026-10-18-review-speed-and-5s-context.md`.
