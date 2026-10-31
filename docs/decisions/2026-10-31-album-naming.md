# 专辑剧集命名 (episode naming per album) — 2026-10-31

Leon (2026-10-31): in 专辑设置 (not 节目设置), each album can say how its episodes are named; several presets,
his own being 编号 + 空格 + 名称, plus a custom one with his own separator / characters.

- Presets: 编号 + 空格 + 名称 (`EP012 奥本海默`), 编号 · 名称, 编号｜名称, 编号：名称, 第几期 + 名称
  (`第12期 奥本海默`), 只用名称; 自定义 = text before the number, between number and name, after the name
  (≤ 12 characters each); 不统一 = titles as typed (what albums made before have).
- A new album starts with 编号 + 空格 + 名称; an existing album keeps 不统一 until a format is picked.
- Applied when an episode is imported into the album: 编号 = the import's 剧集编号, 名称 = the title typed (any
  number / separator typed in front is taken off first, so "EP012 · 奥本海默" becomes "EP012 奥本海默"). The
  import form shows 「这一集会叫：…」.
- Episodes already in the album are renamed only with 「把已有的 N 集也按这个格式改名…」, after a question that
  lists before → after. Only the title in episode.json changes. Moving an episode into an album renames nothing.

Code: `lacuna_app/naming.py`, `lacuna_app/routes/album_naming.py`, `web/src/features/album-naming/`; tests
`tests/app/test_album_naming.py`, `web/e2e/album_naming.spec.ts`.
