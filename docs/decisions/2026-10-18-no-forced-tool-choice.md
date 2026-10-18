# Structured AI answers never force the tool

Date: 2026-10-18 (Leon's validation, V6)

The current models think before they answer and refuse a forced tool (`tool_choice` `{"type": "tool"}` or
`{"type": "any"}`) with a 400. 「记住」 rewrite, 本集学到的规则 summary and the 配乐 assistant used it, so all
three failed and showed "AI not connected" (the summary page even showed the raw English error).

Decision: every AI call that wants a structured answer uses `tool_choice: auto` with a strict tool, the
system prompt names the tool, and a plain-text answer is asked for once more
(`lacuna_app/ai_tools.py: call_tool`). `tests/app/test_lessons.py::test_no_module_forces_a_tool` fails if
any module forces a tool again.

Failures reach Leon as a short reason in the interface language (`error_message`, e.g.「AI 服务返回错误（400）」),
never the raw API text; a summary error stored before this change is shown as「AI 服务出了点问题」.
