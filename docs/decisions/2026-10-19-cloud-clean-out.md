# Cloud clean-out: everything but habits and learned rules (2026-10-19)

Leon's recordings are no longer on his computer, so the cloud episodes can't be repaired. He asked
(thread 「声音播放不了」, 19:41Z) to delete everything except habits and the rules LACUNA learned, on
production and staging, then test the whole product himself. He confirmed the written list at 22:03Z,
EP001_样本集 included (his earlier "never delete EP001" no longer applies).

- Deleted: every episode of the main workspace (the way 「永久删除」 does it, so review verdicts and chat
  are snapshotted into `learning/` first), the media library incl. series rules, exports, import caches,
  the app's copies of recordings.
- Kept: `learning/` (habits, rules, 本集学到的规则), accounts and invites, other workspaces, show settings,
  corrected names, AI usage log, speech models.
- How: `lacuna_app/clear_once.py`, run once at startup in cloud mode (marker `.cleared-2026-10-19`).
  Staging clears its copy when the PR is on staging; production when it merges. Staging's later copies
  of production carry the marker. Removed in a later release.
- Undo: the nightly encrypted R2 backup from before the clean-out.

Follow-up (22:30Z): both sites ran it; the code is removed. One miss: the import list keeps jobs in
memory (Importer, built by routes/appinfo.py before the clean-out ran), so 生化危机's finished import
still showed until the next restart even though its files were gone. The restart that ships this
removal clears it. Lesson: a startup clean-out must also drop in-memory state built before it.
