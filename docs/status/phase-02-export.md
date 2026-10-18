# Phase 2 — 导出成品

State: **done with #4** (导出 is now its own step in the episode flow + the primary button under the title, phase 8; validation by Leon pending listening verdict)

What Leon gets: 一个按钮导出整集 WAV / MP3（-16 LUFS / -1 dBTP），带进度，导出后能在文件夹里找到

Depends on: 母带与导出 thread merged (`lacuna_core`) · Parallel with: 3

## Progress
- **Mastering + export** (2026-10-17, D36): 导出 → stereo 24-bit WAV + 128 kbps MP3 in `<workspace>/exports/<episode>/` (+ JSON record), -16 LUFS / ≤ -1 dBTP, gentle chain (`lacuna_core/master.py`, `export.py`, `lacuna_app/exporter.py`). Validated on Leon's PC with full raw EP001 (Leon +7 dB): in -17.4 LUFS / +5.5 dBTP → out -16.14 LUFS / -1.30 dBTP; compressor mean 0.95 dB; limiter active 0.5 %; MP3 -16.6 LUFS / -1.46 dBTP; 73.5 min in ~5 min, ~145 MB RAM. Leon's own 最终成品.mp3 measures -17.9 LUFS / +4.4 dBTP (clipping). Listening pair in `exports\EP001_mastering_test\` (A_before_preview / B_after_master, from 60:22).
- Export renders the final mix incl. music (phase 6a) and the per-track host gains set at import / on 「声音」 (`levels.md`) through the same chain.

## Open issues
- Mastering: MP3 comes out ~0.4 LU quieter than the WAV (LAME low-pass); app preview still soft-clips (preview is not mastered). Tuning of compressor/limiter awaits Leon's listening verdict.
- 2026-10-18 perf pass (#106): true peak measured in blocks on threads, export WAV + MP3 264.7 s → 231.5 s on the cloud box, files byte-identical (`docs/status/perf.md`).
