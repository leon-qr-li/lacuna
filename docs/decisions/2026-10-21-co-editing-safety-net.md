# Several people in one episode: the safety net (option A)

- Date: 2026-10-21
- Status: CONFIRMED (Leon put it on the pre-beta list as batch 4; assessment
  `/mnt/project-files/lacuna/docs/多人同时剪辑评估_2026-10-20.md`, option A). Live co-editing (option B: push,
  cursors, paragraph locks, per-person AI chat) stays for after beta; option C (CRDT) is not done.

1. **Version number.** Every save of an episode's edit state adds 1 to `rev` (in `state.json`, returned by
   `GET /api/episodes/<id>`). Each edit remembers at which `rev` and by whom it was last changed (`touched`).
2. **409 for stale decisions.** A review decision (`keep` / `restore` / `apply`, and 全部通过) carries the `rev` the
   page showed. If someone else changed that edit after it, the server answers 409 with `stale: true` and a message
   naming them; nothing changes, and the page loads the latest. Decisions on edits nobody else touched go through.
   Manual cuts already refuse overlaps; requests without `rev` (older pages) are not checked.
3. **409 for stale text saves.** Show notes (`PUT /api/episodes/<id>/publish`) and 节目设置 (`PUT /api/show`) carry a
   `rev` too; a save from an older version is refused instead of silently overwriting. Show notes keep what the
   person typed under the latest text to copy from; 节目设置 refills the form with what is stored.
4. **Auto refresh.** The episode page says hello every 5 s (and when the tab comes back);
   when `rev` went up it loads the latest without a reload (the playhead stays).
5. **Presence.** The same heartbeat returns who else has the episode open (「pei 也在这一集」), named by the part of
   their sign-in email before the @. Held in memory only; a page silent for 20 s has left.
6. **Per-person undo.** Undo / redo history entries record who made them. Ctrl+Z undoes your own latest step even if
   someone else's steps came after it, unless they changed the same edit since (then it is refused, with their name).
   A new step clears only your own redo steps. Steps from before this change count as anyone's.

Without accounts (a local install) there is one editor: no presence, undo works as before, versions still protect
against two tabs. Album settings (`PATCH /api/albums/project`) are not versioned yet (admin-only, rarely edited).
