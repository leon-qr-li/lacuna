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


# ---------------------------------------------------------------- first cut (new-episode import)

def first_cut_ops(a: float, b: float) -> list[dict]:
    """What a real editor would answer for the synthetic conversation (tests/app/synth.py) in the
    raw window [a, b): tool-schema ops (all fields present, unused ones null, points as strings)."""
    from tests.app.synth import tok

    def op(**kw):
        base = {"op": None, "track": None, "category": None, "from": None, "to": None, "at": None,
                "target_s": None, "delta_s": None, "reason": "", "confidence": 0.5}
        return base | kw
    ops = [
        op(op="tighten_pause", track="both", at="4.75", target_s=0.4, category="pause",
           reason="Leon→Pei 接话 1.5s→0.4s", confidence=0.6),
        op(op="cut", track="L", **{"from": tok("L", 18.2), "to": tok("L", 20.0)}, category="repetition",
           reason="同一句话说了两遍，保留第二遍", confidence=0.7),
        op(op="cut", track="both", **{"from": "26.4", "to": "29.7"}, category="content",
           reason="这段题外话和主线无关，后面没有再提", confidence=0.55),
        op(op="tighten_pause", track="both", at="45.0", target_s=0.6, category="pause",
           reason="空白 2.0 秒，收到 0.6 秒", confidence=0.85),
        op(op="cut", track="L", **{"from": "L999999", "to": "L999999"}, category="disfluency",
           reason="不存在的 token，会被丢掉", confidence=0.5),
    ]

    def start(o):
        p = o["at"] if o["op"] == "tighten_pause" else o["from"]
        return float(p) if p[0].isdigit() else 0.0
    return [o for o in ops if a <= start(o) < b]


class _Stream:
    def __init__(self, resp):
        self.resp = resp

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.resp


class FakeFirstCutAnthropic:
    """`client.beta.messages.stream(...)` answering each window request with `first_cut_ops`."""

    def __init__(self, delay: float = 0.0, fail_windows: set[int] | None = None,
                 refuse_windows: set[int] | None = None, refuse_models: set[str] | None = None):
        import re
        self._re = re.compile(r"原始时间 ([\d.]+)–([\d.]+) 秒")
        self.delay = delay
        self.fail_windows = set(fail_windows or ())
        self.refuse_windows = set(refuse_windows or ())
        self.refuse_models = set(refuse_models or ())      # empty = every model refuses those windows
        self.requests: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kw):
        import time
        self.requests.append(kw)
        m = self._re.search(kw["messages"][0]["content"])
        a, b = float(m.group(1)), float(m.group(2))
        if self.delay:
            time.sleep(self.delay)
        if int(a // 600) in self.fail_windows:
            raise RuntimeError("simulated API failure")
        usage = SimpleNamespace(input_tokens=500, output_tokens=900, cache_creation_input_tokens=20000,
                                cache_read_input_tokens=0)
        if int(a // 600) in self.refuse_windows and (not self.refuse_models or kw["model"] in self.refuse_models):
            return _Stream(SimpleNamespace(
                stop_reason="refusal", model=kw["model"], _request_id="req_fake", usage=usage,
                stop_details=SimpleNamespace(type="refusal", category="reasoning_extraction", explanation="x"),
                content=[SimpleNamespace(type="thinking", thinking="")]))
        inp = {"notes": "合成对话：两人聊电影。", "ops": first_cut_ops(a, b)}
        return _Stream(SimpleNamespace(
            stop_reason="tool_use", model=kw["model"], _request_id="req_fake",
            content=[SimpleNamespace(type="tool_use", name="submit_ops", input=inp)],
            usage=SimpleNamespace(input_tokens=500, output_tokens=900, cache_creation_input_tokens=20000,
                                  cache_read_input_tokens=0)))


# ---------------------------------------------------------------- publish pack (phase 9)

def publish_answer(user: str) -> dict:
    """What a real writer would hand back for the transcript in `user`: two parts, an entry every
    other segment, one made-up segment id (must be dropped) and one misheard name."""
    import re
    segs = re.findall(r"^(s\d{4}) \S+ (\S+?)：(.*)$", user, flags=re.M)
    half = max(1, len(segs) // 2)

    def entries(rows):
        return [{"segment": sid, "text": f"{who} 聊到「{text[:6]}」"} for sid, who, text in rows[::2]]
    return {
        "title": "合成的一期：两部电影",
        "alt_titles": ["两部电影一个结尾", "那个结尾到底好不好"],
        "blurb": "两个人聊一部很好看的电影，和它的结尾。",
        "intro": "一个月没见，我们又来聊电影了。\n\n- **第一部**：真的很好看\n- **第二部**：结尾有争议",
        "sections": [{"heading": "暖场", "entries": entries(segs[:half]) + [{"segment": "s9999", "text": "不存在"}]},
                     {"heading": "正题：那个结尾", "entries": entries(segs[half:])}],
        "films": [{"name": "《一部电影》", "note": "结尾"}],
        "shows": ["《Stranger Things》"],
        "things": ["天线宝宝"],
        "glossary": [{"term": "网大", "meaning": "夸人用的，真的。"}],
        "names_to_check": [{"heard": "结尾", "suggested": "结局", "segment": segs[0][0] if segs else None,
                            "why": "上下文是在说电影的结局"}],
    }


class FakePublishAnthropic:
    """`client.beta.messages.stream(...)` answering the publish request with `publish_answer`."""

    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.requests: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kw):
        import time
        self.requests.append(kw)
        if self.delay:
            time.sleep(self.delay)
        inp = publish_answer(kw["messages"][0]["content"])
        return _Stream(SimpleNamespace(
            stop_reason="tool_use", model=kw["model"], _request_id="req_fake",
            content=[SimpleNamespace(type="tool_use", name="submit_publish_pack", input=inp)],
            usage=SimpleNamespace(input_tokens=30000, output_tokens=4000, cache_creation_input_tokens=0,
                                  cache_read_input_tokens=0)))
