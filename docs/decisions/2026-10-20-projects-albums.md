# Projects and albums: a project holds episodes, albums are optional groups with their own defaults

- Date: 2026-10-20
- Status: CONFIRMED（Leon，16:05Z 选 A「专辑封面 + 散集」；16:37Z 用词「邀请协作」；16:43Z 认可全套 14 屏）
- Supersedes / changes: the per-show `series` rules in library.json (show-profile / music-page); `workspaces` (a workspace becomes a project in step 2)

Terms are studio-style: **Project / 项目** (required, at least one, you always work inside one) and
**Album / 专辑** (optional; an episode is in one album or none). Design pages:
https://claude.ai/artifact/DbHfdS7iYbzFAnvvWaU5V9 (options) and https://claude.ai/artifact/4k91rQUwYJcCUmW9h2SeuT (full set).

- 剧集 page, layout A: albums as a row of covers, then 「不在专辑里」 for loose episodes. No albums: today's
  list plus a small 「＋ 新专辑」. One album holding every episode: its strip and its episodes inline, no extra click.
- Album page `#/album/<id>`: strip (cover, name, count, 默认片头 / 默认片尾 with 本专辑 / 沿用项目), import into
  the album, its episodes, 这个专辑的素材. 专辑设置 = name, cover, about, defaults; delete keeps the episodes.
- Defaults: an album's opener / ending **override** the project's, per slot; empty = the project's.
  A new import into an album gets them placed automatically.
- Library scope: 整个项目 / 某个专辑 / 只这一集 (per-episode kept). Deleting an album turns its media into project media.
- Old `series` rules migrate on first read: the default rule → the project, every other rule → an album.
- Collaboration happens only at project level, worded 「邀请协作 / Invite collaborators」, never 「分享」.
- Learned rules and 剪辑力度 are **global** (per editor), not per project.

Built in steps: (1) albums (this PR), (2) several projects: project list and switcher, project settings,
邀请协作 (a workspace becomes a project), (3) learned rules and edit strength global.
