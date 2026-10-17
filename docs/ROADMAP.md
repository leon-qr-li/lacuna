# LACUNA App Roadmap (from POC to app)

_Started 2026-10-17, after Leon passed the POC (AI first cut + sample previews heard on his PC)._

How we work (Leon, 2026-10-17):
- Small phases. Each phase ships to Leon's PC; he validates it before anything that depends on it starts.
- Phases with no dependency between them may run in parallel threads, **at most 2–3 at once** (Leon validates them all). Check dependencies first; quality over speed.
- Every phase report says: what was done, which features were added, and how Leon validates it (what to open, which steps, what counts as pass).
- New ideas from Leon are added here at any time; order is re-checked when they land.

Prerequisites beyond the POC: none block development. Only person-only item: `ANTHROPIC_API_KEY` on Leon's PC (D23), needed from phase 3 on. A second raw episode is needed for phase 4's real acceptance, not to build it.

| # | Phase | What Leon gets | Depends on | Parallel with | State |
|---|---|---|---|---|---|
| 1 | 审阅提速 | 剩下全部通过（一步可撤销）、决定后自动跳到下一条、Y/R 快捷键、过目进度、只看没过目的、AI 未删建议可以“不删，保持原话” | — | 母带与导出 (thread) | **done, validated by Leon 2026-10-17** |
| 2 | 导出成品 | 一个按钮导出整集 WAV / MP3（-16 LUFS / -1 dBTP），带进度，导出后能在文件夹里找到 | 母带与导出 thread merged (`lacuna_core`) | 3 | **done with #4** (top-bar 导出 button; validation by Leon pending listening verdict) |
| 3 | 真 AI 对话 | 聊天框接 Claude API：在任意位置说“这段删掉 / 停顿短一点”，AI 给出可试听的修改 | Leon's API key (set 2026-10-17) | 2 | **done, validated by Leon 2026-10-17** |
| 4 | 新一集导入 | 在 App 里选两条分轨 → 后台跑 ASR、分析、AI 第一刀，任务面板显示进度，完成后直接进入审阅 | 3 (first cut runs through the API at runtime) | 5 | — |
| 5 | 从审阅里学习 (D27) | Leon 的恢复/保留变成规则与阈值校准，下一集第一刀更像他 | Leon's full review of EP001; 3 | 4 | **built (D38)**; Leon's EP001 review = 5 single decisions + 1 batch of 110 → hand edit added as 2nd source; install + validation pending |
| 6 | 片头、配乐与 ducking | 系列片头规则、指定配乐的放置与压低人声下的音乐、素材库 | 2 (mix bus + export) | 5 | — |
| 7 | 打包与更新 | 双击更新（不再靠远程装机）、Mac 实机跑通（Pei） | — (any time; best after 2) | any | — |
| 8 | UI 审美迭代 | 视觉与布局打磨 | flows stable (after 4) | 5–6 | — |
| 9 | 发布资料包 | 标题候选、简介、show notes、成品时间线上的章节、专有名词核对，一键复制 | 2 | 6a | — (plan: `docs/BEYOND_AUDIO_PLAN.md`) |
| 10 | 海报模板 | 节目版式模板 + Leon 的剧照 + 资料包标题 → 封面 PNG | 9 | 6a | — (direction awaits Leon) |
| 11 | 辅助发布 | 发布页（文件、文字、海报、清单、打开上传页）+ 发布/同步状态核实；之后再试浏览器代填 | 9, 10 | — | — |
| 6b | AI 推荐配乐 | AI 提议放音乐/台词的位置，从库里原声的真实分析中给 2–3 个候选片段 | 6, 5 | — | after MVP |

Parallel set (2026-10-17): phase 3 merged (#8), awaiting Leon's validation. Export (phase 2) shipped inside the 母带与导出 thread (#4).

## Phase 1 — 审阅提速 (2026-10-17)
- API: `POST /api/episodes/{id}/review` `{action: approve|keep|restore, ids?}`; one undo step; default = every edit still pending. `approve` signs off the current state (cut stays cut, AI's unapplied suggestion stays unapplied).
- UI: progress meter, 「剩下 N 处全部通过」, auto-advance to the next pending edit after a decision (wraps to skipped ones), `Y` = 通过当前状态, `R` = 恢复原话, 「只看没过目的」 filter, 「不删，保持原话」 for unapplied AI suggestions.
- Tests: `tests/app/test_ai_cut.py::test_batch_review_*`, `web/e2e/ai_cut.spec.ts` (review flow).

## Phase 3 — 真 AI 对话 (2026-10-17)
- Chat goes to Claude (`claude-opus-5-5`, effort low, strict tool `propose_edit`, server-side refusal fallback). Engine: `lacuna_app/editor.py` (`ClaudeEditorAdapter`, `scene`, `resolve`); context from `Episode.chat_context` (`lacuna_app/episode.py`).
- What Claude sees (text + numbers only): instruction, playhead, utterances within ±45 s *as they sound on the current cut* (id, speaker, start/end, text), quiet pauses (id, length), edits within ±30 s (status + removed words), last 6 chat turns with their outcome.
- What Claude can answer: `cut` (utterance range, optional verbatim start/end words), `cut_one_track` (one host, nothing moves), `shorten_pause`, `restore`; several actions per proposal; empty = ask back. `resolve` maps ids/quotes to timeline ranges and drops anything it was not shown (D37).
- Key: `ANTHROPIC_API_KEY` from the environment, else (Windows) from the user/machine environment in the registry, so a server started before `setx` still finds it. UI badge shows Claude / 演示规则 and why. Each call logs tokens / seconds / est. cost to `<workspace>/ai_usage.jsonl` and shows "Claude · 4.2 秒 · ≈$0.015" under the reply.
- Real-key check without touching the episode: `scripts/ai_chat_smoke.py`.
- Tests: `tests/app/test_claude_chat.py` (fake client), `web/e2e/claude.spec.ts` (AI E2E server answers through `ClaudeEditorAdapter` with `tests/app/fake_claude.py`).

## Phase 5 — 从审阅里学习 (2026-10-17, D38)
- Evidence: (1) review decisions per first-cut edit, read from each episode's `state.json` + undo history (`lacuna_app/learning.py: decisions`): kept / restored / accepted / declined / added (chat) / untouched, and how (single decision, batch sign-off, none); (2) Leon's own hand edit of the same recording (`scripts/learn_from_hand_edit.py`, S4 alignment) labels every speech edit and finds long passages he cut that the AI left in. Snapshots in `<workspace>/learning/decisions/` (demo episodes ignored).
- Rules (`learn`): protect (AI cuts a kind too much), review (routine kind he restores → goes to review), trust (consequential kind always agreed → auto-apply up to 5 s speech), timid (AI suggestions he cut), missed (cuts he asked for in chat), taste (content passages he cut vs kept, as examples), threshold (confidence calibration). Weights: single 1, batch 0.5, untouched 0.25, hand edit 0.5. Explicit rules win: hand-edit evidence never argues for cutting Pei's stumbles less (R002).
- Approval (D17): every rule starts as a candidate on the page 「学到的规则」(`#/learning`, link in the top bar). Only approved rules act, frozen as approved; new evidence that changes a rule shows as an update to re-approve.
- Consumers: `learning.prompt_rules(workspace)` → text block for the AI first-cut prompt (phase 4); `learning.review_policy(workspace)` → `convert_ops(..., policy=)` / `needs_review(..., kind, host, policy)` (used by `scripts/make_ai_episode.py`).
- EP001 result (cloud preview from v3 ops + Leon's actual review): 2 candidates: Leon content taste (28 cut / 14 kept examples, 3 passages the AI missed) and "both hosts' 嗯/啊 stumbles cut less" (weak). No routine kind was restored in review, so the review threshold stays.
- Tests: `tests/app/test_learning.py`, `web/e2e/learning.spec.ts`.
