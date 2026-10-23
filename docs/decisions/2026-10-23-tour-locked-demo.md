# The sample tour is a locked demo

Date: 2026-10-23. Decided by Leon (decision card, then in chat).

## Decision
The bubble tour of LACUNA 示例节目 is a demo, "like a PPT":
- LACUNA performs every action a step needs: clicks, timeline selections, chat sends, approvals, export, publish pack and covers.
- The person only presses 知道了.
- The whole page is masked; nothing else can be clicked.
- Every output is fixed in advance: the chat and music answers, the publish pack and the covers.
- The tour has 16 steps in 9 chapters (it had 60, then 30). The last chapter, 发布, shows the publish pack and covers.
- Read, then act (Leon, 2026-10-23 17:40Z): reading and acting never happen at the same time. The bubble shows first
  and nothing moves. Only after 知道了 does LACUNA highlight and act; the result follows in a new bubble. When the
  next step is on another tab, LACUNA visibly presses 下一步 (or the tab) first.

## Why
New people got stuck on the do-steps: where to click, a failed drag, text hidden under a bubble. Then the
sample showed the product "not working". The sample is there to show what LACUNA can do. Teaching by doing
belongs to the guide shown when the person imports their first episode.

## Consequences
- Copy says what LACUNA did ("LACUNA 替你点了…"), never "click …".
- A step whose action fails still moves on after 20 s, so nobody is stuck.
- Before beta, Leon and Pei record the sample (zh + en). Then every detail is polished and locked.
- The tour depends on the pages' markup (`data-tour` / `data-testid`); `web/e2e/tour.spec.ts` walks all of it.
