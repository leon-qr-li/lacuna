# Phase 6a — 片头、配乐与 ducking (= 6a)

State: **built (D45)**; install with the next batch update, then Leon validates

What Leon gets: 系列片头规则、指定配乐的放置与压低人声下的音乐、素材库

Depends on: 2 (mix bus + export) · Parallel with: 9

## Progress
- **Phase 6a media library + music** (2026-10-17, D45): 素材库 page, Claude credit lookup, 配乐 tab with intro / interlude / outro / bed / clip, measured levels and voice-driven ducking, series intro rule, export with music. Merged with the batch; Leon's PC update + validation pending (batch update run by the coordinator). Nothing extra to install (uses ffmpeg/ffprobe already needed). Leon needs to add his EP001 intro / interlude (45:59) / outro music files to the library.
- **6a follow-up: upload + fixed uses** (2026-10-17, D48, Leon's asks while validating): drag files onto 素材库 or pick with the system dialog (server-side folder browser removed there); fixed 用途 dropdown (片头 / 片尾 / 休息间隙 / 聊天背景音 / 电影对白·sample / 预告片 / 其他) that sets the placement role on the 配乐 tab; after a Claude lookup the filled credit fields open for editing. `scripts/make_demo_music.py` makes 3 test tracks (on Leon's PC already; re-run after updating so their uses become 片头 / 休息间隙 / 片尾).
- **6a follow-up: credit lookup needs a note** (2026-10-17, D50): 「让 Claude 查正式曲名」 is disabled until the 备注 has text; the backend also refuses an empty note without calling Claude (no usage spent).

## How it is built (素材库与配乐 (2026-10-17, D45))
- Library page 「素材库」(`#/library`, link in every top bar): add a file through the local folder browser (copied into `<workspace>/library/music|jingles|clips/`) or drop files there and 「扫描文件夹」; per file: player, duration, LUFS, Leon's note, BGM credit with state (已确认 / 待确认 / 还不知道曲名), 「让 Claude 查正式曲名」 (API + web search; text only), 「对，就是这首」, 「手动改」, 「移出素材库」 (file moved to `_removed/`).
- Episode tab 「配乐」 (`#/ep/<id>/music`): 成品试听 (final mix stream incl. music and ducking), series suggestion (用系列片头片尾 / 这一集不用), placements (片头 / 间奏 / 片尾 / 铺底 / 台词) with in/out, overlap with the voice, gain, 「试听这一处」, 「去掉」; add form with position in final-cut time (m:ss); 「记成系列片头片尾」; BGM credit list as the show notes will print it.
- Engine: `lacuna_core.InsertGap`; `lacuna_app/library.py`, `lacuna_app/music.py`. Export renders the final mix (voice + music, stereo music as hard-panned L/R) through the same mastering chain; the export record lists the music credits.
- For phase 9: `music.bgm_credits(ws, id)`, `music.final_time(ws, id, t)`, `music.final_duration(ws, id)`.
- Tests: `tests/app/test_music.py`, `tests/app/test_music_api.py`, `tests/test_edl.py::test_insert_gap_*`, `web/e2e/music.spec.ts`.

## Open issues
- Music (6a): no undo for music placements (remove + add again); chat cannot place music yet ("这里放《XX》的主题曲" via chat is a follow-up); the export popover's "stale" hint ignores music changes. Ducking depth / levels (LEVEL_LU, DUCK_DB in `music.py`) await Leon's listening verdict.
