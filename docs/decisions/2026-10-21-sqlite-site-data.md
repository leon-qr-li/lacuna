# Site-wide data moves to one SQLite file; episodes stay plain files

Date: 2026-10-21. Decided by Leon (batch 3 decision pack, question 1, option A; 「全选 A」 03:01Z).
Supersedes / changes: "plain JSON storage until DB switch" (project memory); `storage` status notes.

## Decision
`<root>/lacuna.db` (lacuna_app/db.py) holds what the whole site shares and the admin pages will query:
accounts, sessions, invites, settings (`config`), shows and their members, plans, 申请试用 requests and the
event log. Episode files (transcripts, edits, renders, caches) stay plain files in each show's folder.

- One connection per process, one lock, every change a `BEGIN IMMEDIATE` transaction; schema versions by
  `PRAGMA user_version` (append to `db.SCHEMA`, never edit an old entry).
- Each table keeps the record as JSON (`data`) next to the columns worth querying, so the code that owns a
  record keeps working with plain dicts.
- Migration on first start: users.json / sessions.json (auth) and spaces.json (shows) are read into the
  database once (marker in `meta`); the old files stay 30 days, then are removed. Rolling the code back
  within those 30 days finds the old files untouched (changes made after the move would be missing).
- Backups: after changes, at most every 10 minutes, SQLite's backup API writes `lacuna-snapshot.db`
  (written aside, then renamed), so the nightly restic copy always holds one consistent database.

## Why
The admin pages (counts, funnels, retention) and plans need queries across all accounts and shows; JSON
files rewritten whole on every change don't scale to that and can't be updated together atomically.
SQLite is a file on the same encrypted volume: no new service, no cost.
