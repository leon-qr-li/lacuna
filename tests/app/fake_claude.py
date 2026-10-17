"""A scripted stand-in for `anthropic.Anthropic` used by the E2E server (no key, no network).

It answers like the real producer would for a few instructions: "恢复" restores the closest
applied edit before the playhead, "停顿" shortens the longest pause nearby, anything else cuts
the utterance at the playhead.
"""
from __future__ import annotations

import json
from types import SimpleNamespace


def _act(type_, **kw):
    a = {"type": type_, "from_utterance": None, "to_utterance": None, "start_text": None, "end_text": None,
         "pause": None, "target_s": None, "edit": None}
    return a | kw


def decide(sc: dict) -> dict:
    said, t = sc["instruction"], sc["playhead"]
    if "恢复" in said:
        cands = [e for e in sc["nearby_edits"] if e["status"] == "applied" and e["at"] <= t + 0.5]
        if not cands:
            return {"message": "附近没有可以恢复的改动。", "title": "", "reason": "", "confidence": 0.0,
                    "category": "chat", "actions": []}
        e = max(cands, key=lambda e: e["at"])
        return {"message": f"把「{e['title']}」恢复成原话。", "title": f"恢复：{e['title']}", "reason": "按你的指令",
                "confidence": 0.9, "category": "chat", "actions": [_act("restore", edit=e["id"])]}
    if "停顿" in said:
        p = max(sc["pauses"], key=lambda p: p["length"] - abs(p["start"] - t) / 10)
        return {"message": f"把 {p['start']:.0f} 秒处 {p['length']:.1f} 秒的停顿收到 0.4 秒。",
                "title": f"停顿 {p['length']:.1f}s → 0.4s", "reason": "按你的指令", "confidence": 0.9,
                "category": "pause", "actions": [_act("shorten_pause", pause=p["id"], target_s=0.4)]}
    u = next(u for u in sc["utterances"] if u["id"] == sc["playhead_utterance"])
    return {"message": f"删掉 {u['speaker']} 这句「{u['text']}」。", "title": f"删除 · {u['text'][:8]}",
            "reason": "按你的指令删除这句话", "confidence": 0.7, "category": "content",
            "actions": [_act("cut", from_utterance=u["id"])]}


class FakeAnthropic:
    def __init__(self):
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        sc = json.loads(kw["messages"][0]["content"])
        return SimpleNamespace(
            stop_reason="tool_use", model=kw["model"], _request_id="req_fake",
            content=[SimpleNamespace(type="tool_use", name="propose_edit", input=decide(sc))],
            usage=SimpleNamespace(input_tokens=2500, output_tokens=300, cache_creation_input_tokens=0,
                                  cache_read_input_tokens=0))
