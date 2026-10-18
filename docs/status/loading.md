# 统一的加载提示 (unified loading)

State: **current look is round 2, style C「信号」 (PR #74, merged); round 1 PR #64 (style A) validated 2026-10-17 19:28Z** · thread「统一的加载提示」 · decision `docs/decisions/2026-10-17-unified-loading.md`

What shipped in round 1 (style A「声波」, picked by Leon 2026-10-17 18:58Z; look replaced by round 2):
- `web/src/features/loading/`: `Loading.tsx` (Wave, Skel, EpisodeListSkeleton, PageLoading, Waiting, BusyLabel,
  JobProgress, TopLine), `activity.ts` (non-GET requests counter, wired into `req` in `web/src/api.ts`), CSS, English.
- Used on: home list, episode screen, 素材库, 配乐, 发布资料, 海报, 上传喜马拉雅, 学到的规则, 设置 (page loads);
  import (6 steps with per-step %, ETA), export, publish pack, poster, update download (long jobs);
  AI chat, review "用一句话调整" (had no indicator before), title lookup (让 LACUNA 查正式曲名), music assist, A/B render,
  dictation, library uploads (short waits). Review "原话" no longer shows the previous edit's text while loading.
- E2E `web/e2e/loading.spec.ts` (held responses: placeholders, page loading, top line on/off).

Round 2 (2026-10-17 20:21Z ask, decision `docs/decisions/2026-10-17-loading-logo.md`): the mark is now the logo's
pulse line with a sunset glint running along it and a breathing ON AIR dot; bar and top line use the logo gradient.
Same component API, no page changes.
2026-10-18 (PR #92): `JobProgress` takes an optional `left` (server-side estimate); the importer passes it.

Next (round 2): Leon's validation not recorded yet; he checks after the batch update (refresh 首页 → three grey cards, not blank; open an episode / tab;
send a chat line; export).
