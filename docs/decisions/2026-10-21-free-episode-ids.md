# Deleting an episode frees its ID; its learning evidence is filed away

- Date: 2026-10-21
- Status: CONFIRMED (Leon put it on the pre-beta list, batch 4; analysis
  `/mnt/project-files/lacuna/docs/习惯与剧集绑定分析_2026-10-20.md`)
- Replaces: "a deleted episode's id is retired for good" (full scan 2026-10-18)

When an archived episode is deleted for good, its learning evidence under `learning/decisions|asks|lessons|chats/`
is renamed from `<id>.json` to `<id>@<YYYY-MM-DD>-<4 hex>.json`, and every `"episode"` name inside the file
(also `<id>.hand_edit`) is rewritten to the new name (`lacuna_app/archive.py: file_away`). The id can be used by a
new episode at once, with no prompt; that episode starts with no review snapshot, lessons, asks or chat of its own.

- Habits are still never deleted: 学到的规则 reads every file in those folders, so the evidence keeps counting.
  Sources read as 「EP003（已删）」 on the learning page.
- Each file is moved first (atomic), then relabelled, so a crash never counts evidence twice.
- The 「按 AI 原样算」 mark for that id is dropped from the person's rules file (it is already in the snapshot).
- Migration: ids retired before this change are freed the same way by `free_deleted_ids` (at start, when the import
  form asks for the next id, and before an import takes an id). `direct` (rules added directly) is not an episode
  and is left alone, as is the evidence of every episode that still exists (archived ones included).
- The suggested next id no longer skips deleted ids, so after deleting EP003 the form may propose EP003 again.
