# V6 — 「记住」 / 本集学到的规则 / 配乐助手 AI 调用报错

State: fixed on branch `claude/project-thread-isj68t` (PR pending merge). Decision:
`docs/decisions/2026-10-18-no-forced-tool-choice.md`.

- `lacuna_app/ai_tools.py` `call_tool`: auto tool_choice, the prompt names the tool, one retry on a text answer.
- `lessons.py` (rewrite + summary) and `music_assist.py` use it; failures become readable reasons
  (`draft.error`, `lesson.error`, summary `error`); old raw summary errors are masked.
- Web: RememberCard / LessonsView say「这次没能改写（原因）」instead of「没接上 AI」when a key exists.
- Tests: pytest (retry, 400 → readable zh/en, legacy error masked, no forced tool anywhere), E2E
  `web/e2e/ai_errors.spec.ts`.

Next: none; Leon validates in the batched release sweep.
