# 统一的加载提示 (unified loading)

State: **merged in PR #64, waiting for the batch update** · thread「统一的加载提示」 · decision `docs/decisions/2026-10-17-unified-loading.md`

What shipped (style A「声波」, picked by Leon 2026-10-17 18:58Z):
- `web/src/features/loading/`: `Loading.tsx` (Wave, Skel, EpisodeListSkeleton, PageLoading, Waiting, BusyLabel,
  JobProgress, TopLine), `activity.ts` (non-GET requests counter, wired into `req` in `web/src/api.ts`), CSS, English.
- Used on: home list, episode screen, 素材库, 配乐, 发布资料, 海报, 上传喜马拉雅, 学到的规则, 设置 (page loads);
  import (6 steps with per-step %, ETA), export, publish pack, poster, update download (long jobs);
  AI chat, review "用一句话调整" (had no indicator before), Claude credit lookup, music assist, A/B render,
  dictation, library uploads (short waits). Review "原话" no longer shows the previous edit's text while loading.
- E2E `web/e2e/loading.spec.ts` (held responses: placeholders, page loading, top line on/off).

Next: Leon validates after the batch update (refresh 首页 → three grey cards, not blank; open an episode / tab;
send a chat line; export).
