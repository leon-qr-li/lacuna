# Projects & albums

Decision `projects-albums`. Thread 节目与系列设计.

## State (2026-10-20)
- Step 1 — albums: built on branch `claude/project-thread-66xo8m`.
  - Server: `lacuna_app/albums.py` (albums.json per workspace, covers under `albums/<id>/`, migration from
    library.json series rules), `lacuna_app/routes/albums.py`; library scopes gain `albums`; music defaults
    album → project; import takes `album` and places the defaults.
  - Web: `web/src/features/albums/` (cover row, album page `#/album/<id>`, dialog, 移到专辑 menu);
    Home and ImportPanel wired; library / music page use 整个项目 / 专辑 / 本集.
  - Tests: `tests/app/test_albums.py`, `web/e2e/albums.spec.ts` (light, dark, English).
- Not yet: 「让 LACUNA 画」 album cover from the mockup (upload + gradient only).

## Next
- Step 2: several projects (list, switcher, project settings tabs, 邀请协作, rename 工作区 → 项目, 节目 nav → project settings).
- Step 3: learned rules + 剪辑力度 global across projects.
