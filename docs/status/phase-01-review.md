# Phase 1 — 审阅提速

State: **done, validated by Leon 2026-10-17**

What Leon gets: 剩下全部通过（一步可撤销）、决定后自动跳到下一条、Y/R 快捷键、过目进度、只看没过目的、AI 未删建议可以“不删，保持原话”

Depends on: — · Parallel with: 母带与导出 (thread)

## How it is built (审阅提速 (2026-10-17))
- API: `POST /api/episodes/{id}/review` `{action: approve|keep|restore, ids?}`; one undo step; default = every edit still pending. `approve` signs off the current state (cut stays cut, AI's unapplied suggestion stays unapplied).
- UI: progress meter, 「剩下 N 处全部通过」, auto-advance to the next pending edit after a decision (wraps to skipped ones), `Y` = 通过当前状态, `R` = 恢复原话, 「只看没过目的」 filter, 「不删，保持原话」 for unapplied AI suggestions.
- Tests: `tests/app/test_ai_cut.py::test_batch_review_*`, `web/e2e/ai_cut.spec.ts` (review flow).
