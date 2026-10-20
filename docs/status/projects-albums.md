# Projects & albums

Decision `projects-albums`. Thread 节目与系列设计.

## State (2026-10-20)
- Step 1 — albums: LIVE (PR #151, merged 2026-10-20 18:52Z after Leon's 通过).
  - Server: `lacuna_app/albums.py` (albums.json per workspace, covers under `albums/<id>/`, migration from
    library.json series rules), `lacuna_app/routes/albums.py`; library scopes gain `albums`; music defaults
    album → project; import takes `album` and places the defaults.
  - Web: `web/src/features/albums/` (cover row, album page `#/album/<id>`, dialog, 移到专辑 menu);
    Home and ImportPanel wired; library / music page use 整个项目 / 专辑 / 本集.
  - Tests: `tests/app/test_albums.py`, `web/e2e/albums.spec.ts` (light, dark, English).
- Not yet: 「让 LACUNA 画」 album cover from the mockup (upload + gradient only).

- Step 2 — several projects: one PR with step 3.
  - Server: anyone signed in may start a project (`POST /api/spaces`, moves them in); project name = its
    show name; `/api/spaces/{id}/people|invite|invites/{iid}`; who invited whom (`added_by`). Inviting someone
    without an account stays with LACUNA's owner/admins (Leon asked to choose A/B, 2026-10-20 ~17:30Z).
  - Web `web/src/features/projects/`: project menu after LACUNA in every top bar, #/projects (landing with
    two or more projects), new project dialog, #/project settings tabs (基本信息 / 主持人 / 片头片尾 / 发布 /
    协作者), #/invite (邀请协作 top-bar link for managers). 节目 link gone; #/show redirects. 工作区 → 项目 in UI.

- Step 3 — habits follow the editor (decision `habits-follow-the-editor`): same PR as step 2.
  - Server: `lacuna_app/habits.py` (person's home, level, host adjust), `routes/habits.py` (`/api/habits`);
    show hosts keep `cut_adjust`; `learning.Learning.path` = the person's home; dispatcher sets `habits.HOME`;
    `routes/spaces.habits_moved` copies old approvals once at the first request.
  - Web: `web/src/features/habits/` (设置 → 剪辑习惯 card); host select 比我平时更狠 / 一样 / 更松.
  - Tests: `tests/app/test_habits.py`, `web/e2e/habits.spec.ts`.

## Next
- Steps 2 + 3 PR: staging (after #153) and Leon's 通过.
