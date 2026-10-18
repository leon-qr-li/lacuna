# Phase 3 — 真 AI 对话

State: **done, validated by Leon 2026-10-17**

What Leon gets: 聊天框接 Claude API：在任意位置说“这段删掉 / 停顿短一点”，AI 给出可试听的修改

Depends on: Leon's API key (set 2026-10-17) · Parallel with: 2

## How it is built (真 AI 对话 (2026-10-17))
- Chat goes to Claude (`claude-opus-5-5`, effort low, strict tool `propose_edit`, server-side refusal fallback). Engine: `lacuna_app/editor.py` (`ClaudeEditorAdapter`, `scene`, `resolve`); context from `Episode.chat_context` (`lacuna_app/episode.py`).
- What Claude sees (text + numbers only): instruction, playhead, utterances within ±45 s *as they sound on the current cut* (id, speaker, start/end, text), quiet pauses (id, length), edits within ±30 s (status + removed words), last 6 chat turns with their outcome.
- What Claude can answer: `cut` (utterance range, optional verbatim start/end words), `cut_one_track` (one host, nothing moves; since 2026-10-18 an erase filled with that host's room tone, `review-edit.md`), `shorten_pause`, `restore`; several actions per proposal; empty = ask back. `resolve` maps ids/quotes to timeline ranges and drops anything it was not shown (D37).
- Key: `ANTHROPIC_API_KEY` from the environment, else (Windows) from the user/machine environment in the registry, so a server started before `setx` still finds it. UI badge shows LACUNA / 演示规则 and why (the interface never names the vendor, `dialog-brand.md`). Each call logs tokens / seconds / est. cost to `<workspace>/ai_usage.jsonl` and shows "LACUNA · 4.2 秒 · ≈$0.015" under the reply.
- Before the AI editor (`routes/episodes.py` chat): volume asks ("我的声音太低") are answered locally (`levels.chat_volume`, `levels.md`), and 「记住」 turns into a draft rule to confirm (`lessons.py`, phase 5); neither calls the editor.
- Real-key check without touching the episode: `scripts/ai_chat_smoke.py`.
- Tests: `tests/app/test_claude_chat.py` (fake client), `web/e2e/claude.spec.ts` (AI E2E server answers through `ClaudeEditorAdapter` with `tests/app/fake_claude.py`).

## Open issues
- Phase 3 (real Claude chat, D37) merged (#8). Real-key check on Leon's PC 2026-10-17 (separate worktree, copy of EP001_AI): key found via registry-user, 3/3 real calls OK, 6–13 s and $0.03–0.04 per turn; pause and sentence cuts sensible, vague "跑题" ask got a clarifying question. Cost per turn logged to `<workspace>/ai_usage.jsonl`. Leftover dirs on his PC: `C:\Projects\lacuna_p3check`, `C:\Projects\lacuna_p3check_ws` (safe to delete).
