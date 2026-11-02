# Episode naming (剧集起名与改名) — status

Decision: `docs/decisions/2026-11-02-episode-naming.md`.

## State (2026-11-02)
- Built: rename API (`GET/PUT /api/episodes/{id}/name`), publish ↔ episode name sync, top-bar pencil,
  「改名」 on home and album cards, publish title pick list with 自己写一个 and 撤销, 还没起名 on cards,
  import field 「这一集叫什么」 with a hint when empty.
- Tests: `tests/app/test_episode_name.py`; E2E `episode_name.spec.ts` (both themes, phone width) and the
  updated `publish.spec.ts`. Publish / poster unit tests now start from an unnamed episode so the pack keeps
  LACUNA's title.

## Open
- Leon to check on lacunastudio.app after deploy.
- Packs written before this change have no `suggested`; the list falls back to title + alternatives.
