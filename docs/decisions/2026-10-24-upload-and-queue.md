# Uploads survive page changes; every show's imports wait in one server-wide queue

- Date: 2026-10-24
- Status: Claude 技术决策（第五批，Leon 2026-10-24 定的「上线前加固」范围）
- Supersedes / changes: — (analysis `docs/上传与并发分析_2026-10-20.md`)

Speech recognition is the memory peak of the server (about 2–3 GB per import). Before, a second import on the
same show was refused and imports on two shows ran at once. Now every show's imports pass one gate
(`lacuna_app/import_queue.py`, `LACUNA_IMPORT_SLOTS`, default 1): a second episode waits and shows
「排队中，前面还有 N 集」; the AI first cut leaves the gate (it waits on the network) so the next import starts.
Uploads in pieces keep going when the user visits another page (`web/src/features/import/draft.ts`), the top bar
shows progress, leaving the site or switching shows asks first, a piece is retried for about 2 minutes, and a
finished upload is moved into place without a copy. The cloud updater's busy check counts imports, exports,
publishing and uploads of every show, so a deploy never restarts mid-upload. A new import under an old episode id
drops the old cached steps unless the tracks are the same files. Resumable uploads across a closed browser stay
after launch.
