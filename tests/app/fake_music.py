"""Scripted stand-in for Claude on the music page (docs/decisions/2026-10-17-music-suggestions.md)."""
from __future__ import annotations

import json
from types import SimpleNamespace



def music_answer(ctx: dict) -> dict:
    """A tiny stand-in for LACUNA arranging music: understands 晚/早 N 秒, 小/大 3 dB, 去掉, 加间奏."""
    text = ctx["instruction"]
    by_role = {p["role"]: p for p in ctx["placements"]}
    role = next((r for k, r in (("间奏", "interlude"), ("片头", "intro"), ("片尾", "outro"), ("背景", "bed"))
                 if k in text), "interlude")
    p = by_role.get(role)

    def act(type_, **kw):
        base = {k: None for k in ("placement_id", "asset_id", "role", "at_s", "until_s", "shift_s", "gain_db",
                                  "gain_change_db", "src_in_s", "src_out_s", "solo_s", "ramp_s", "ramp_out_s", "bg_db",
                                  "pre_s", "bye_s", "fade_out_s")}
        return {"type": type_, **base, **kw}

    if "加" in text and role == "interlude" and p is None:
        asset = next(a for a in ctx["library"] if a["use"] == "休息间隙")
        at = ctx["longest_pauses"][0]["at_s"]
        return {"message": f"在 {ctx['longest_pauses'][0]['at']} 加一段间奏。",
                "actions": [act("add", asset_id=asset["asset_id"], role="interlude", at_s=at)]}
    if p is None:
        return {"message": "现在没有这段配乐，你想放哪一首？", "actions": []}
    if "去掉" in text:
        return {"message": f"把{p['role_label']}去掉。", "actions": [act("remove", placement_id=p["id"])]}
    if "dB" in text or "小" in text or "大" in text:
        d = -3.0 if "小" in text else 3.0
        return {"message": f"{p['role_label']}音量 {d:+.0f} dB。",
                "actions": [act("set", placement_id=p["id"], gain_change_db=d)]}
    n = 2.0 if "两" in text else 1.0
    return {"message": f"{p['role_label']}往{'后' if '晚' in text else '前'}挪 {n:.0f} 秒。",
            "actions": [act("move", placement_id=p["id"], shift_s=n if "晚" in text else -n)]}


class FakeMusicAnthropic:
    def __init__(self, answer=None):
        self.answer, self.calls = answer or music_answer, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        ctx = json.loads(kw["messages"][0]["content"])
        usage = SimpleNamespace(input_tokens=1500, output_tokens=150, cache_read_input_tokens=0,
                                cache_creation_input_tokens=0)
        tool = SimpleNamespace(type="tool_use", name="arrange_music", input=self.answer(ctx))
        return SimpleNamespace(stop_reason="tool_use", content=[tool], usage=usage, model="claude-opus-5-5")
