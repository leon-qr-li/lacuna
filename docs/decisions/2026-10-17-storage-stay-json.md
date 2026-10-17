# Storage stays plain JSON; only the 3 most recent episodes stay in memory

Date: 2026-10-17 · Asked by Leon ("要不要改数据库？"), analysis `docs/STORAGE_ANALYSIS.md`.

- Keep per-episode JSON files with atomic write + `.bak` (`lacuna_app/store.py`). Measured: 430 KB `state.json` for a 73-min episode with 647 edits, ~16 ms per save; torn writes are already prevented. A database would not fix the real gaps (no backups, one `.bak` generation) and does not help sharing with Pei (SQLite in a sync folder is worse than JSON).
- Switch to SQLite when learning or search must query across ~100+ episodes, or two people edit the same episode. The storage layer stays swappable.
- Leon: automatic backups not now.
- Leon: keep only the 3 most recently used episodes in memory, load the others on demand (`AppContext.get` LRU + weak map so one Episode object per episode). The home page list reads `episodes/.index.json` (rows keyed by mtime+size of `episode.json`/`state.json`), not every episode. 100 episodes: list 0.035 s, open an uncached episode 0.12 s.
- Sharing with Pei, when it comes: separate workspaces + an episode package; store media paths relative / resolve by sha256 (paths are absolute Windows paths today).
