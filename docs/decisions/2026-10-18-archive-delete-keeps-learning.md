# Archive hides an episode; deleting for good removes only the episode's own files, never learning

- Date: 2026-10-18
- Status: CONFIRMED（Leon 2026-10-17 22:00Z for the principle）; details are a Claude 技术决策
- Supersedes / changes: —

首检 #3. Archiving writes one line to `<workspace>/archive.json`; nothing inside the episode moves, so
restoring is exact and the archived episode still opens by URL. Only an archived episode can be
deleted for good (the shared in-app confirmation, red button). Deleting removes the episode
folder, its import cache `imports/<id>/` (so a new import under the same id starts clean) and the
copies the app made of dragged-in tracks (`imported_tracks/`). It keeps `learning/` (before the folder
goes, the episode's review verdicts are snapshotted to `learning/decisions/<id>.json` and its chat log
copied to `learning/chats/<id>.json`, so asks not yet summarized survive), `exports/<id>/` (finished
files Leon may have published) and any recording outside the workspace (Leon's own downloads; the app
only ever read them). The folder is first renamed into `episodes/.trash/` in one step: if Windows has a
file open the rename fails and nothing is deleted.
