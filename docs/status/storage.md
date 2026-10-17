# Storage: JSON vs database, episode memory

## Done
- 2026-10-17 analysis `docs/STORAGE_ANALYSIS.md` (measured on Leon's workspace); decision `docs/decisions/2026-10-17-storage-stay-json.md`.
- Only the 3 most recently used episodes stay in memory (`lacuna_app/server.py` `AppContext.get/peek/loaded`); home list from `episodes/.index.json` (`lacuna_app/episode_index.py`); music view no longer pins closed episodes; learning page walks episodes one at a time. Tests `tests/app/test_episode_cache.py`.

## Open
- Learning page (`/api/learning`) still re-reads every episode (~0.1 s each, ~9 s at 100 episodes): refresh only episodes whose `state.json` changed since their decisions snapshot. Coordinate with the phase 5 thread (it owns `learning.py`).
- Not now (Leon): automatic JSON backups, pre-update snapshot. Needed before the first schema change (rollback would otherwise leave episodes unopenable).
- `names.json` / `learning/rules.json` read-modify-write without a lock (tiny lost-update risk).
- Pei sharing: absolute media paths in `state.json`.
