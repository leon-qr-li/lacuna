# 剧集起名与改名 (episode name: import, publish pick, rename any time) — 2026-11-02

Leon (2026-11-02): three situations. (1) He already has a name at import: type it there. (2) No name yet: at
发布, LACUNA offers several titles to pick from, and the pick becomes the episode's name on the home page too.
(3) The name can always be changed. Design page https://claude.ai/artifact/UjsqFqFE8xpbCNbWtEtKcg; Leon took
every recommendation.

- Rename from two places: a pencil next to the name in the episode's top bar (click the name or the pencil,
  Enter saves, Esc cancels) and 「改名」 on the home / album episode card (in-app dialog; the phone's way in).
- One name everywhere: a title picked on 发布资料 renames the episode (toast with 撤销), a rename sets the
  publish pack's title, a title switched through the pack API renames the episode, and a name-check fix
  applied on 发布资料 fixes the episode's name too.
- Named at import: the pack is written with that name as its title (the number taken off); LACUNA's titles
  are kept as `draft.suggested` and listed under it. On the publish page the user's name is first, tagged 你起的.
- Not named: the title is only the number (`EP012`, or the album format with an empty 名称). The home card
  says 还没起名; 发布资料 says 这一集还没起名 and nothing is selected until a pick. Renaming to empty goes back
  to this state (the 撤销 of a first pick).
- In an album with a naming format only the 名称 is typed; the number and separators are kept
  (`naming.title`), and the dialog shows what the episode will be called.
- Only episode.json's title (and the pack's title) change; edit, audio and the rest of the publish notes stay.

Code: `lacuna_app/episode_name.py`, `lacuna_app/routes/episode_name.py`, `web/src/features/episode-name/`;
tests `tests/app/test_episode_name.py`, `web/e2e/episode_name.spec.ts`, `web/e2e/publish.spec.ts`.
