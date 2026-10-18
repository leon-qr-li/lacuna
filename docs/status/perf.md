# Code and performance pass (2026-10-18 night full scan)

Rule for every change here: behaviour unchanged, and wherever an output can be compared, it is
**byte-identical** to before (ASR JSON, tokens, features, editor document, AI ops, learning JSON,
exported WAV/MP3). Measurements: 4-core cloud box, a 73.5-min two-track rehearsal pair made by
`scripts/rehearsal/make_long_episode.py` (real sherpa-onnx ASR, scripted first cut), 359 edits.

## Measured

| Path | before | after | how |
|---|---|---|---|
| Whole import (73.5 min × 2 tracks) | 578 s | 351 s | below |
| ASR per track | 253 / 282 s | 163 / 163 s | Paraformer and SenseVoice decode each segment at the same time (`asr.transcribe`) |
| Next track's 16 kHz decode | in series | while the previous track is recognised | `importer._steps` |
| Features (pauses, pitch, overlap) | 24.4 s | 7.3 s | pitch frames in blocks on a thread pool; `_fill_runs` vectorised |
| 学到的规则 page, `GET /api/learning` (3 such episodes) | 1689 ms | 145 ms | `Episode.words` bisects a per-track index |
| Home list, `GET /api/episodes` (warm) | 26 ms | 9 ms | one `summary()` per row, not per field |
| Export WAV + MP3 (profiled both times) | 264.7 s | 231.5 s | true peak measured in overlapping blocks on threads |

Unchanged and already fast: episode open ~50 ms, review keep/restore ~65 ms, edit text ~5 ms,
first audio range ~10 ms, UI bundle 355 kB JS (local, served with ETags).

On Leon's PC (Ryzen 5 3600, 6 cores / 12 threads) each ASR model already ran 6 threads; running
both at once fills all 12, so the import gain there is likely smaller than −39 % but not negative.

## Where the remaining time goes
- Import: ASR is ~90 %. VAD is ~26 s per track (single-threaded Silero); it could be overlapped
  with recognition by streaming segments, not done (more moving parts for ~10 %).
- Export: ffmpeg's MP3 encode is ~54 s (single-threaded LAME) and the three mastering passes
  re-render the timeline each time (~9 s per pass). Piping pass 3 straight into the encoder would
  save most of the encode time but must reproduce libsndfile's 24-bit quantisation to stay
  identical; not done.

## Cleanup
- `store.now_iso()` is the one helper for stored timestamps (chat_learning keeps microseconds).
- Removed: `/api/fs` + `importer.list_dir`, web `api.fs` / `api.episodes` / `FsListing`,
  `i18n.reply_language` / `Lang`, `editor.key_source`, unused imports/locals (ruff F clean).
- AI first-cut window cache is written atomically; a torn window file is cut again on 继续.
- Race fixed (#106): the 海报 / 发布资料 views read the document before the job, so a poll landing
  as the job finished could see "done" next to the old document (no cover / no pack until a
  reload; also the flaky `test_upload_checklist_api` / `test_poster_api` under CI load). The job
  is now read first.
- Bugs found while scanning and handed to the 全面测试与修复 thread (fixed in #105): double poll
  chains on 发布资料/海报, 401 from uploads/dictation not signing in again, ffmpeg-missing message,
  half-decoded temp files.

## Known duplicates left on purpose (each differs in behaviour; merging would change output)
- Seconds → clock text: `publish.mmss` (always zero-padded for 小宇宙), `editor._fmt` (no hours),
  `chat_learning._mmss` vs `music_assist._mmss` (truncate vs round).
- Byte sizes on the web: Upload/Poster show MiB, Archive/Import show SI MB/GB. Unifying is a
  visible text change; left for a product decision.
- Two playback-speed controls (player bar 1/1.5× vs review 1–2× remembered).
- The seven Claude client wrappers differ in timeout, retries and when they read the key.

## PRs
- #104 import (merged), #106 learning page + export + cleanup.
