# 配乐上传进度条 (music upload progress) — 2026-10-31

Leon asked for a progress bar when uploading music. Every music upload (素材库, 配乐页「从电脑添加」, 专辑页
「给这个专辑添加素材」) shows one row per file: a bar with percent and MB sent (and time left after a few
seconds), 「排队中」 for files waiting their turn, then 「已传完，正在读取音频…」 while the server reads the
file. One-request uploads go through XMLHttpRequest (fetch can't report upload progress); big files already go
in pieces (`upload-parts`), which report their own progress.

Code: `web/src/features/upload-progress/`, `web/src/features/library/api.ts` (`uploadAsset`); test
`web/e2e/upload_progress.spec.ts`.
