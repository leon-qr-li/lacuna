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

- Step 2 — several projects: built locally on `local/projects-step2` (pushed after #151 merges).
  - Server: anyone signed in may start a project (`POST /api/spaces`, moves them in); project name = its
    show name; `/api/spaces/{id}/people|invite|invites/{iid}`; who invited whom (`added_by`). Inviting someone
    without an account stays with LACUNA's owner/admins (Leon asked to choose A/B, 2026-10-20 ~17:30Z).
  - Web `web/src/features/projects/`: project menu after LACUNA in every top bar, #/projects (landing with
    two or more projects), new project dialog, #/project settings tabs (基本信息 / 主持人 / 片头片尾 / 发布 /
    协作者), #/invite (邀请协作 top-bar link for managers). 节目 link gone; #/show redirects. 工作区 → 项目 in UI.

## Next
- Step 3: learned rules + 剪辑力度 global across projects.
