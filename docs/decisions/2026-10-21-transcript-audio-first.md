# Transcript proofreading: the audio is the truth, terms are sound-alike hints only

- Date: 2026-10-21
- Status: CONFIRMED（Leon, 2026-10-20 23:10Z）
- Supersedes / changes: system-terms-auto-proofread, transcript-terms

Leon's case: project "TEST Project", hosts LI / WANG, real 洛城二三事 audio came out as
「欢迎你来听TEST Project / 我是LI / 我是WANG / 一期EPISODE」. Host names, the project name and the episode
title are no longer forced into the transcript. A proposed fix is kept only when the heard word and the term
sound alike (pypinyin romanisation, difflib ratio ≥ 0.4, same onset class, length ratio ≥ 0.4;
`transcript_fix.sounds_alike`). The prompt (prompts/transcript_fix.txt) says the same. Transcripts proofread
by version 1 are repaired once (`undo_forced`, CHECK_VERSION 2). Each project can list its own 专有名词
in 项目设置 → 基本信息 (show.json `terms`). Regression test: tests/app/test_transcript_fix.py (Leon's case).
