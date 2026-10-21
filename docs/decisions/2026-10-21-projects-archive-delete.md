# Project picture, colour, archive and permanent delete

- Date: 2026-10-21
- Status: CONFIRMED（Leon, 2026-10-20 23:52Z: 1 A 2 A 3 A 4 A）
- Supersedes / changes: projects-albums (adds)

- Picture: square; managers upload any image, cut to a centred 256 px PNG (`auth/pictures/<id>.png`).
  Without one a project shows its own solid colour (the least used of 10, picked at creation) with its
  first letter.
- Archive: by the project's managers (or LACUNA owner/admins). It moves to 「已归档」 on 所有项目 and is
  read-only for every collaborator (the dispatcher refuses every change) until a manager restores it.
- Delete for good: only from 已归档, only by the project's creator or LACUNA's owner, typing the project's
  name. Deletes the project folder (episodes, albums, library, exports), its picture, its pending invites.
  The main project can't be deleted, nor your only project. Learned rules and 剪辑力度 are the person's
  own already; the project's learning evidence (`learning/` minus rules.json) is first copied into the
  deleting person's store under `learning/from_projects/<id>-<time>/`. Backups expire on their own.
