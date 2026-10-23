# Cover posters are included in the plan: no price, 3 rounds per episode

Date: 2026-10-23. Decided by Leon (option A).

## Decision
- The poster page shows no price. That means no "一共约 $1", no "约 $x" per version, and no "会再花一次 AI 的钱".
  Drawing covers is part of the subscription, like every other AI use (AI pricing decision B, PR #148).
- Each episode gets `poster.MAX_ROUNDS` = 3 rounds of 「画 4 版」.
  - A round counts only when at least one version is drawn.
  - When the rounds are used up, the button reads 「本集海报次数用完」 and the server refuses with the same text.
- The sample show's covers are pre-drawn and cost nothing, so they have no cap.

## Why
The per-generation price was left over from per-use billing. Users should not have to think about money for a
cover. A round costs cents, which fits in the per-hour AI budget.

## Consequences
- Revisions (「改一改」, one version each) are not capped yet. The per-user monthly AI cap in batch 5 hardening
  covers them.
- Tests: `tests/app/test_poster.py::test_three_rounds_per_episode_then_none_left`, `web/e2e/poster.spec.ts`.
