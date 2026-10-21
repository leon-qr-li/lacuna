# Polish round after batch 2 (2026-10-21)

Leon's findings while validating PR #160 on prod, all built in one PR (list: project-files
`lacuna/docs/本轮polish清单_2026-10-21.md`).

1. **Invite email body = copy A 「六步流程」**: after the lead line, a numbered list of an episode's six steps from
   import to publish (导入分轨 → LACUNA 初剪 → 逐处审阅 → 配乐与响度 → Show notes 与封面 → 导出发布), in the designed and
   the plain-text mail, zh and en. `lacuna_app/invite_mail.py` `steps()`.
2. **Six-box code input**: a click on a box selects that digit and typing replaces it; a failed try empties the
   boxes and puts the cursor in the first; paste and autofill unchanged. Verification logic untouched.
   `web/src/features/auth/TwoStep.tsx` `CodeInput` (`wrong` prop).
3. 「去看学到的规则」 opens 学到的规则 on its 已生效 tab (`#/learning/approved`).
4. Timeline legend: each swatch + label is one item, items at an even 16 px gap.
5. **Episode tile shows the chosen cover**: `/api/episodes` rows carry `poster` (the chosen version's preview URL,
   cache-busted by poster.json's mtime) or null; the tile falls back to the letter.
6. **节目设置 side nav** like 设置: groups 基本 (基本信息 / 主持人 / 片头片尾 / 发布) and 团队 (协作者).
7. **Home title** = the project's avatar + name; 「专辑」 and 「剧集 · N 集」 subheadings stronger; the top-bar
   link 「剧集」 is now 「首页」 / Home. English counts use singular/plural ("1 episode"); the album strip's
   "Default outro" no longer wraps.
8. 项目 → 节目 everywhere in the interface: decision `show-not-project`.
