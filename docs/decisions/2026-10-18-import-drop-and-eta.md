# Import takes dropped tracks (copied into the workspace); time left is estimated per step on the server

- Date: 2026-10-18
- Status: Claude 技术决策
- Supersedes / changes: phase 4's folder browser (`GET /api/fs` stays, unused by the UI)

首检 #4: the import form now works like the media library: drop zone + 「选择文件」 (the system file
dialog), plus a drop target per track and a swap button. A browser never reveals a dropped file's path,
so the bytes go to the local app (`POST /api/imports/tracks`, octet-stream only, 127.0.0.1) and are kept as
`<workspace>/imported_tracks/<token>/<name>`; the import reads that copy read-only. Copies the form lets
go of are removed at once, unused ones after a day; deleting the episode for good removes its copies.
Cost: a second copy of the raw audio on disk (~0.5–1.5 GB per episode) while the episode exists.

首检 #5: the old 「预计还要」 extrapolated elapsed time over the whole bar, whose step weights are fixed
shares, so it was badly off (40 min episode, first cut 1/4 → "about 2 minutes"). The server now estimates
(`lacuna_app/import_eta.py`): the current step from its own speed blended with history, the AI first cut
modelled as first window alone then 3 in parallel (from the real first-window time), and the steps to
come from this machine's past imports (median seconds per audio minute; measured defaults otherwise).
Every step now records its seconds in job.json. 「每段约 10 分钟」 meant ten minutes of recording per
window, not time, and now says so (「每段约 10 分钟录音」).
