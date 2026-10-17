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
| 2 | 导出成品 | 一个按钮导出整集 WAV / MP3（-16 LUFS / -1 dBTP），带进度，导出后能在文件夹里找到 | 母带与导出 thread merged (`lacuna_core`) | 3 | waiting on dep |
| 3 | 真 AI 对话 | 聊天框接 Claude API：在任意位置说“这段删掉 / 停顿短一点”，AI 给出可试听的修改 | Leon's API key (set 2026-10-17) | 2 | in progress (own thread) |
| 4 | 新一集导入 | 在 App 里选两条分轨 → 后台跑 ASR、分析、AI 第一刀，任务面板显示进度，完成后直接进入审阅 | 3 (first cut runs through the API at runtime) | 5 | — |
| 5 | 从审阅里学习 (D27) | Leon 的恢复/保留变成规则与阈值校准，下一集第一刀更像他 | Leon's full review of EP001; 3 | 4 | — |
| 6 | 片头、配乐与 ducking | 系列片头规则、指定配乐的放置与压低人声下的音乐、素材库 | 2 (mix bus + export) | 5 | — |
| 7 | 打包与更新 | 双击更新（不再靠远程装机）、Mac 实机跑通（Pei） | — (any time; best after 2) | any | — |
| 8 | UI 审美迭代 | 视觉与布局打磨 | flows stable (after 4) | 5–6 | — |

Parallel set (2026-10-17): 母带与导出 + phase 3 (each in its own thread). Phase 2 starts after the export core merges.

## Phase 1 — 审阅提速 (2026-10-17)
- API: `POST /api/episodes/{id}/review` `{action: approve|keep|restore, ids?}`; one undo step; default = every edit still pending. `approve` signs off the current state (cut stays cut, AI's unapplied suggestion stays unapplied).
- UI: progress meter, 「剩下 N 处全部通过」, auto-advance to the next pending edit after a decision (wraps to skipped ones), `Y` = 通过当前状态, `R` = 恢复原话, 「只看没过目的」 filter, 「不删，保持原话」 for unapplied AI suggestions.
- Tests: `tests/app/test_ai_cut.py::test_batch_review_*`, `web/e2e/ai_cut.spec.ts` (review flow).
