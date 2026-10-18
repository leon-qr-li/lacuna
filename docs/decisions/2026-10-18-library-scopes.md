# The media library has two scopes: 公共 (shared) and 本集 (an episode's own)

- Date: 2026-10-18
- Status: CONFIRMED（Leon, 2026-10-18 spec）
- Supersedes / changes: D45 (library model; adds scope metadata, nothing else changes)

Each library asset carries `shared: bool` and `episodes: [episode ids]`. The file is stored once (the
asset id is still the content hash); scope is only metadata. Assets indexed before this (no fields)
are shared; an asset that is neither shared nor in any episode is treated as shared rather than lost.

- 「挪到某一集」 keeps any other episode whose music already plays the asset in its list (the reply
  names them), so its music page still offers what it plays and deleting the target episode can't take it.
- 素材库 page: new files go to 公共 or into a chosen episode (「加到」 next to 用途); each asset shows its
  scope and has 「挪到某一集」 (this episode only), 「设为公共」 and 「也加到另一集」; the list filters by
  全部 / 公共 / one episode's own. The same file added again joins where it was added (shared, or one
  more episode).
- 配乐 page: offers only shared assets and this episode's own (`GET /api/library?episode=`); its new
  「从电脑添加」 upload belongs to this episode. `POST …/music` refuses another episode's asset (422);
  auto placement and the music chat see the same subset (a series rule's intro / outro still applies).
- Placements reference the asset id, so changing scope never breaks music already placed anywhere,
  and credits stay with the asset (show-notes BGM credits unchanged).
- Archiving an episode touches no asset. Deleting it for good (`archive.py`) drops it from every
  asset's list and removes the assets that were only its own the library's usual way (file to
  `library/_removed/`). Kept instead: shared assets, assets of another episode, assets another
  episode's music (placements or draft) still uses (they now belong to those episodes), and a
  series rule's intro / outro (made shared). `learning/` is never touched.
