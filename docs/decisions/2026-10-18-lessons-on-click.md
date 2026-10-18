# 本集学到的规则 runs only when Leon clicks 总结, and never re-proposes a 「记住」 he decided

- Date: 2026-10-18
- Status: Leon's ask while validating v2026.10.18.4 (V11)
- Changes: 2026-10-18-confirmed-learning (the step started its summary on the first visit)

- Steps can be opened in any order, so opening the step must not assume the episode is finished: nothing
  runs until he clicks 总结. The intro says "如果这一集已经剪完了，请点「总结」…". A summary error stored by a
  version before V6 (raw API error) is shown as "not summarized yet", not as an error.
- 「记住」 turns are not sent to the summariser at all: a confirmed one is already a rule, a 不用 is final.
  Their titles (and his words) also go to `already_reviewed` and filter the answer, in case the same ask
  appears in an ordinary chat turn.
