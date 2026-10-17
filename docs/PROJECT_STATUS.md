# LACUNA Studio — Project Status

_Last updated: 2026-10-17 02:55Z (phase 3 validated); prev 2026-10-17 02:20Z_

## Current phase
POC passed (Leon, 2026-10-17). Building the app in small phases per `docs/ROADMAP.md` (D34). App phase 1 (审阅提速) done and validated by Leon on his PC (main a719a8a). Mastering + export merged (#4). Phase 3 (real AI chat, #8/#9) installed on Leon's PC (main 5b13662) and validated by Leon 2026-10-17.

## Done
- Assessment `docs/00_TECH_LEAD_ASSESSMENT.md`; decisions `docs/DECISIONS.md` (D23–D32); hardware `docs/HARDWARE_PROFILE.md`; editorial rules `docs/EDITORIAL_RULES.md` (R001–R003).
- Workspace on Leon's PC: `C:\Projects\LACUNA_Workspace\` (EP001 raw + reference). EP001 is a full raw/final pair (D29).
- Spikes: S2 ASR → Paraformer (D30); S4 alignment → 470 cuts, per-track editing (D31); S3 engine `lacuna_core/` (0 clicks, 204× RT).
- S5 AI first cut: v1 blind (too conservative) → v2 with rules learned from first half, scored on held-out half: length 1830 s vs Leon 1806 s, event recall L/P 0.71/0.79, but content-trim precision 0.44. See `spikes/s5_first_cut/REPORT.md`.
- App vertical slice (`lacuna_app/` + `web/`): full listen, voice/chat change → A/B preview → approve, edit review, restore/undo. Demo episode = EP001 10:00–20:00 with Leon's real cut positions.
- **Installed and running on Leon's Windows PC** (2026-10-17): `C:\Projects\lacuna`, start with `C:\Projects\LACUNA_Start.bat` → http://127.0.0.1:8765/. 57/57 tests pass there incl. EP001 integration. Windows fixes in PR #1 (awaiting Leon's merge).
- CI (`.github/workflows/ci.yml`): runs only what a change can affect: docs-only → nothing; `web/` only → UI build + E2E; Python → pytest + build + E2E; CI config/unknown → all. Whatever runs, runs on windows/macos (Apple Silicon)/ubuntu. Merge gate = the single **CI ok** check (green also when nothing needed to run). Claude merges its own PRs when CI ok is green (Leon, 2026-10-17).
- UX wireframes: https://claude.ai/artifact/1BvHmxW54dWCS9kFPyumqV (`design/wireframes/`).
- **AI first cut in the app** (2026-10-17): `lacuna_app/ai_cut.py` + `scripts/make_ai_episode.py` turn S5 edit ops into reviewable edits (title "EP001 · AI 第一刀", no demo marks). Review = content / interjection / > 1.5 s speech / non-pause conf < 0.4, content first then by duration (`lacuna_app/review.py`, D33). v2 held-out ops on full EP001: 384 ops → 367 edits (163 to review), 17 skipped (same pause positions the S5 scorer rejects), 73:32 → 67:08. Episode timeline now derived in one batch sweep (`lacuna_core.apply_batch`): ~570-edit episode opens in ~150 ms, restore/undo ~90 ms, A/B ≤ 0.4 s, server RSS < 0.5 GB. Screenshot `screenshots/04_ai_cut_review.png`.

- **On Leon's PC** (2026-10-17, main 7bc041e): episode `EP001_AI` ("EP001 · AI 第一刀", v3 ops) built in `C:\Projects\LACUNA_Workspace`: 646 edits, 114 to review, 73:32 → 59:43; 107/107 pytest there. Start with `C:\Projects\LACUNA_Start.bat`.
- **Mastering + export** (2026-10-17, D36): top-bar 导出 → stereo 24-bit WAV + 128 kbps MP3 in `<workspace>/exports/<episode>/` (+ JSON record), -16 LUFS / ≤ -1 dBTP, gentle chain (`lacuna_core/master.py`, `export.py`, `lacuna_app/exporter.py`). Validated on Leon's PC with full raw EP001 (Leon +7 dB): in -17.4 LUFS / +5.5 dBTP → out -16.14 LUFS / -1.30 dBTP; compressor mean 0.95 dB; limiter active 0.5 %; MP3 -16.6 LUFS / -1.46 dBTP; 73.5 min in ~5 min, ~145 MB RAM. Leon's own 最终成品.mp3 measures -17.9 LUFS / +4.4 dBTP (clipping). Listening pair in `exports\EP001_mastering_test\` (A_before_preview / B_after_master, from 60:22).

- **Phase 5 learning built** (2026-10-17, D39): `lacuna_app/learning.py`, page 「学到的规则」, `scripts/learn_from_hand_edit.py`. Leon's EP001 review read on his PC (read-only): 5 single decisions (kept 3 big content trims, restored 凤凰形态 15.7 s, applied the 秦格雷 suggestion) + 「全部通过」110; 0 routine restores. Too little alone → his hand edit of EP001 added as second evidence source. Rules need his approval before they act. Installed on Leon's PC (main bae39ef) and **validated by Leon 2026-10-17**.
- **Phase 4 new-episode import** (2026-10-17, D41): Home → 导入新一集 → pick Leon/Pei tracks → local ASR (Paraformer + SenseVoice, sherpa-onnx) → features → Claude first cut in ~10-min windows → review. Resumable per step (`<workspace>/imports/<id>/`). Real ASR verified on sherpa test clips in the cloud box; full EP001 run on Leon's PC pending (needs `pip install -e ".[asr]"`, first import downloads ~400 MB of models).
  - 2026-10-17 first real run on Leon's PC (EP001 raw, 73.5 min): models download ~30 s, ASR Leon 268 s + Pei 197 s, features ~20 s, peak RAM ~1.5 GB. Claude step refused on Opus (D44) → first cut now Sonnet 5.5. After the batch update (main aae392a) the job resumed: Sonnet 5.5, 8 windows, 0 refusals, 8 min 50 s, $2.12; 273 ops → 272 edits, 64 to review (EP001_AI had 646). Episode EP001_导入测试 on Leon's PC awaiting his review. Formal acceptance needs a second episode's raw tracks.
- **Chat voice input** (2026-10-17, D43): 🎤 button next to the chat box; local SenseVoice, text lands in the box, Leon sends. Needs the models from a first import (`<workspace>/models`).
- **Phase 6a media library + music** (2026-10-17, D45): 素材库 page, Claude credit lookup, 配乐 tab with intro / interlude / outro / bed / clip, measured levels and voice-driven ducking, series intro rule, export with music. Merged with the batch; Leon's PC update + validation pending (batch update run by the coordinator). Nothing extra to install (uses ffmpeg/ffprobe already needed). Leon needs to add his EP001 intro / interlude (45:59) / outro music files to the library.

- **Phase 9 publish pack built** (2026-10-17, D46): episode page 「发布资料」 → Claude writes title / blurb / show notes from the current cut's transcript (text only), timeline times computed locally on the final cut, Markdown in the D40 format, copy = rich text + Markdown, chapters, name check (corrections remembered in `names.json`), local re-timing after later edits. BGM from the 6a library once it lands (placeholder until then). Validated by Leon 2026-10-17 on EP001_AI with the real Claude ("我很喜欢这个 show note").

## Open issues
- `EP001_demo` now shows 0 to review under the D33 rule (its fake confidences are ≥ 0.45, no content category). Demo is superseded by EP001_AI; delete or regenerate it.
- Content-trim selection is taste: phase 5 turns Leon's cut/kept passages into examples for the first-cut prompt (D39); effect measurable only on a new episode (phase 4).
- Pause shaping too uniform (keeps 2 vs Leon's 41 pauses >1 s); interjection moves should come from asymmetric per-track pause cuts.
- Phase 3 (real Claude chat, D37) merged (#8). Real-key check on Leon's PC 2026-10-17 (separate worktree, copy of EP001_AI): key found via registry-user, 3/3 real calls OK, 6–13 s and $0.03–0.04 per turn; pause and sentence cuts sensible, vague "跑题" ask got a clarifying question. Cost per turn logged to `<workspace>/ai_usage.jsonl`. Leftover dirs on his PC: `C:\Projects\lacuna_p3check`, `C:\Projects\lacuna_p3check_ws` (safe to delete).
- One-track `tighten_pause` while the other host talks is skipped (needs per-track re-timing in the episode model); counted in `ai_report`. No per-track loudness edit in the AI path yet (D31).
- Review threshold (D33) tuned to v3: 114 of 646 edits to review. AI confidences are poorly calibrated (almost all 0.5–0.6); recalibrate from Leon's first full review.
- Mastering: MP3 comes out ~0.4 LU quieter than the WAV (LAME low-pass); app preview still soft-clips (preview is not mastered). Tuning of compressor/limiter awaits Leon's listening verdict.
- Music (6a): no undo for music placements (remove + add again); chat cannot place music yet ("这里放《XX》的主题曲" via chat is a follow-up); the export popover's "stale" hint ignores music changes. Ducking depth / levels (LEVEL_LU, DUCK_DB in `music.py`) await Leon's listening verdict.
- Missing: task panel, asset inbox, topic labels. macOS is verified only by CI (no real Mac run yet).

## Next action
0. Phase 3 (real chat) per ROADMAP; then phase 4 (new-episode import). Phase 2 (export) shipped with #4.
1. Leon reviews "EP001 · AI 第一刀" (v3, full episode) on his PC; learn from his restores/approvals (D27) and recalibrate review threshold + content-trim taste.
2. Leon sets ANTHROPIC_API_KEY (steps given 2026-10-17; anthropic SDK installed on his PC) → verify real chat end to end.
3. Leon listens to the mastering A/B and an exported EP001_AI; tune chain if needed.
