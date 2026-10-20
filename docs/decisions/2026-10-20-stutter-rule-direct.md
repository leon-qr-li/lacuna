# Stutter rules added directly, without the confirmation step (2026-10-20)

Leon asked (thread 「口吃重复必剪规则」, 16:59Z; wording confirmed 18:28Z) for two learned rules to go
straight in, skipping the usual 「记住」 / 本集学到的规则 confirmation:

1. **Character stutters are always cut.** When Leon or Pei says the first character of a word twice
   (游游戏, 电电影, 开开发), the extra character goes, no "sounds natural" exception.
2. **Clean cuts only, above every rule.** If the stutter is very short, swallowed, unclear, or runs into
   the next character so the cut could clip another word: cut only if nothing around it can be damaged,
   otherwise leave it.

Whole-word repeats (这个这个) are not covered; the older rules on them (Leon: cut to one, ~5 % may stay;
Pei: keep at most two) stay in force. Rule 1 says the 5 % allowance does not apply to character stutters.

How: `lacuna_app/stutter_rule_once.py`, run once at startup in cloud mode on the main workspace (marker
`.rule-stutter-2026-10-20`). The rules are ordinary confirmed asks (source `direct`) adopted on
学到的规则, so the AI first cut reads them via `learning.prompt_rules` from the next import on, and Leon
can withdraw them there like any other rule. Removed in a later release once both sites ran it.
