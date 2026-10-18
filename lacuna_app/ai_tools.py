"""Asking the model for a structured answer through one tool, without forcing the tool.

Forced tool_choice ({"type": "tool"} / {"type": "any"}) is refused (400) by the current models, which
think before answering, so every structured call uses {"type": "auto"}: the tool is strict, the system
prompt names it, and an answer that comes back as plain text is asked for once more."""
from __future__ import annotations

import time
from typing import Any, Callable

AUTO = {"type": "auto"}


def tool_rule(name: str) -> str:
    return f"\n\nAlways answer by calling the {name} tool exactly once; never answer in plain text."  # i18n-ignore


def tool_input(resp: Any, name: str) -> dict | None:
    for block in getattr(resp, "content", None) or []:
        if getattr(block, "type", "") == "tool_use" and getattr(block, "name", "") == name:
            return dict(block.input)
    return None


def call_tool(create: Callable[..., Any], req: dict, name: str, attempts: int = 2) -> tuple[dict | None, Any, float]:
    """-> (the tool's input or None, the last response, seconds). `req` is a messages.create request with
    `tools`; tool_choice is set to auto and the system prompt told to use `name`. Errors propagate."""
    req = dict(req, tool_choice=AUTO)
    if not str(req.get("system", "")).endswith(tool_rule(name)):
        req["system"] = str(req.get("system", "")) + tool_rule(name)
    t0 = time.monotonic()
    resp = None
    for _ in range(max(1, attempts)):
        resp = create(**req)
        out = tool_input(resp, name)
        if out is not None or getattr(resp, "stop_reason", "") in ("refusal", "max_tokens"):
            return out, resp, time.monotonic() - t0
    return None, resp, time.monotonic() - t0
