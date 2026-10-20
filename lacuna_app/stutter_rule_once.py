"""Leon's stutter rules, added directly (Leon 2026-10-20; decision 2026-10-20-stutter-rule-direct).

Leon asked for two rules to go straight in, without the usual 「记住」 / 本集学到的规则 confirmation
(he confirmed the wording in his thread, 18:28Z):
1. a character stutter (the first character of a word said twice: 游游戏, 电电影) by Leon or Pei is always
   cut down to one, with no "sounds natural" exception;
2. above every rule: a stutter is only cut where the cut cannot damage the words around it.
Whole-word repeats (这个这个) stay with the older rules, which are left as they are.

Run once, at startup, on the main workspace of the cloud server (production and staging); a marker file
makes it run once. The rules are ordinary confirmed asks (chat_learning.ChatAsks, source ``direct``) in
force on 学到的规则, so the next AI first cut reads them through ``learning.prompt_rules``.
This module goes away in a later release, once both sites have run it.
"""
from __future__ import annotations

from .chat_learning import ChatAsks
from .learning import Learning
from .store import Workspace, now_iso

MARKER = ".rule-stutter-2026-10-20"
EPISODE = "direct"                      # the asks file these rules are stored under (no episode)

RULES = [
    {"id": "stutter-char-20261020",
     "title": "Leon 和 Pei 字的口吃（一个词开头的字卡了又重说，比如「游游戏」「电电影」「开开发」）"  # i18n-ignore
              "一定剪掉多出来的字，没有商量。整个词说两遍（「这个这个」）不归这条管。",  # i18n-ignore
     "instruction": "Character stutters by EITHER host, Leon or Pei: when the first character of a word comes out "
                    "twice (游游戏, 电电影, 开开发, 我我觉得), ALWAYS cut the extra character so the word is said once "  # i18n-ignore
                    "(游戏, 电影, 开发). No exceptions: the 'about 5% may stay because it sounds natural' allowance of "  # i18n-ignore
                    "older rules does NOT apply to character stutters. Whole-word repeats (这个这个, 电影电影) are "  # i18n-ignore
                    "not covered here; older rules on them stay. Use category \"disfluency\", confidence 0.8. The "
                    "\"clean cuts only\" rule still comes first."},
    {"id": "stutter-clean-cut-20261020",
     "title": "剪口吃前先看能不能剪干净（压过所有规则）：字太短、吞音、说不清，或挨得太紧会碰掉别的字时，"  # i18n-ignore
              "剪了不伤别的部分就剪，会伤到就不剪。",  # i18n-ignore
     "instruction": "CLEAN CUTS ONLY - this overrides every other rule, including the stutter rule: before "
                    "cutting a stutter, check that the cut can be made cleanly. If the stuttered sound is very "
                    "short, swallowed or unclear, or runs into the next character so the cut could clip a "
                    "neighbouring word: cut it only if nothing around it can be damaged; if it could be, leave the "
                    "stutter in. Never damage other words to remove a stutter."},
]


def done(ws: Workspace) -> bool:
    return (ws.root / MARKER).exists()


def run(ws: Workspace, learning: Learning | None = None, asks: ChatAsks | None = None) -> list[str]:
    """Put the rules in force (as if Leon had adopted them on 学到的规则); returns their rule ids."""
    learning = learning or Learning(ws)
    asks = asks or ChatAsks(ws)
    out = []
    for r in RULES:
        asks.put(EPISODE, {"id": r["id"], "title": r["title"], "instruction": r["instruction"],
                           "source": "direct", "quotes": []})
        rid = f"ask:{r['id']}"
        learning.undelete(rid)
        learning.decide(rid, "approve")
        out.append(rid)
    (ws.root / MARKER).write_text(now_iso() + "\n", encoding="utf-8")
    return out
