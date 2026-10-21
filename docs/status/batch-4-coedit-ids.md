# Batch 4: free episode IDs + co-editing safety net (2026-10-21)

Thread 第四批 (branch `claude/project-thread-bbcn14`). Decisions: `docs/decisions/2026-10-21-free-episode-ids.md`,
`docs/decisions/2026-10-21-co-editing-safety-net.md`.

## Done
- Deleting an episode files its learning evidence away as `<id>@<date>-<rand>` and frees the id; migration frees
  ids retired earlier (`lacuna_app/archive.py`). Learning page shows 「EP003（已删）」.
- Episode `rev` + `touched`, per-person undo / redo (`lacuna_app/episode.py`), who is editing (`lacuna_app/coedit.py`,
  set by the dispatcher in `routes/spaces.py`), presence + stale 409 (`routes/coedit.py`), versioned show notes and
  节目设置 saves (`publish.py`, `show.py`, `routes/show.py`).
- Web: `features/coedit/` (heartbeat, auto refresh, 「… 也在这一集」 badge); stale handling in `App.tsx` `run`,
  `PublishView`, `ShowForm`.
- Tests: `tests/app/test_free_episode_ids.py`, `tests/app/test_coedit.py`, updated archive / full-scan tests;
  E2E `web/e2e/coedit.spec.ts` (two accounts) and the stale step in `web/e2e/publish.spec.ts`.

## Open / next
- Album settings are not versioned (admin-only).
- Option B (live push, cursors, per-person AI chat) after beta.
- Leon + Pei multi-person editing test on prod (pre-launch must-do).
