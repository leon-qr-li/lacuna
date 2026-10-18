"""A scripted stand-in for the rule writer (lacuna_app/lessons.py) used by tests and the E2E server.

It answers like the real one would: a rewrite never repeats Leon's words as they are, a correction
is applied to the current version, and an episode summary cites real chat turns / review edits.
"""
from __future__ import annotations

import time


class FakeRuleWriter:
    available = True

    def __init__(self, delay: float = 0.0, lessons: list[dict] | None = None, boom: bool = False):
        self.delay, self.lessons, self.boom = delay, lessons, boom
        self.calls: list[tuple[str, dict]] = []

    def _usage(self) -> dict:
        return {"model": "fake", "input_tokens": 1200, "output_tokens": 200, "seconds": self.delay, "cost_usd": 0.004}

    def rewrite(self, payload: dict) -> tuple[dict, dict]:
        self.calls.append(("rewrite", payload))
        time.sleep(self.delay)
        if self.boom or "AI 出错测试" in payload["said"]:     # E2E: a failed rewrite (V6)
            raise RuntimeError("network down")
        said = payload["said"].rstrip("。.!！")
        same = next((r["id"] for r in payload["existing_rules"] if r["title"].startswith(said[:6])), "")
        if payload.get("current"):
            fb = payload["feedback"].rstrip("。")
            title = f"{payload['current']['title']}（{fb}）"
            return {"title": title, "understood": f"我按你说的改了：{fb}。", "instruction": f"Revised: {fb}.",
                    "same_as": same}, self._usage()
        return {"title": f"每一期都照做：{said}",
                "understood": f"我理解的是：以后每一集剪的时候都按「{said}」来，不只是这一处；片头片尾也一样。",
                "instruction": f"In every episode: {said}.", "same_as": same}, self._usage()

    def summarize(self, payload: dict) -> tuple[list[dict], dict]:
        self.calls.append(("summarize", payload))
        time.sleep(self.delay)
        if self.boom:
            raise RuntimeError("network down")
        if self.lessons is not None:
            return self.lessons, self._usage()
        out = []
        chat, review, rules = payload["chat"], payload["review"], payload["existing_rules"]
        said = [c for c in chat if "跑题" in c["leon_said"]] or [c for c in chat if not c["leon_said"].startswith("记住")]
        if said:
            chat = said
            out.append({"title": "Leon 跑题的段落剪狠一点", "instruction": "Cut Leon's digressions harder.",
                        "why": f"你在第 {chat[0]['turn']} 句让我删了一段跑题的话。", "relation": "new",
                        "related": "", "turns": [chat[0]["turn"]], "edits": []})
        if review:
            r = review[0]
            out.append({"title": "长停顿收到 0.4 秒", "instruction": "Tighten long pauses to 0.4 s.",
                        "why": "这一集 AI 收紧的停顿你都保留了。", "relation": "new", "related": "",
                        "turns": [], "edits": [r["edit"]]})
        if rules and (chat or review):
            r = rules[0]
            out.append({"title": r["title"], "instruction": "Same as before.", "why": "这一集又出现了同样的情况。",
                        "relation": "reinforce", "related": r["id"],
                        "turns": [chat[-1]["turn"]] if chat else [], "edits": [review[0]["edit"]] if review else []})
        return out, self._usage()
