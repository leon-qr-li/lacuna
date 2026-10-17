# Phase 5 — 从审阅里学习 (D27)

State: **done, validated by Leon 2026-10-17** (D39)

What Leon gets: Leon 的恢复/保留变成规则与阈值校准，下一集第一刀更像他

Depends on: Leon's full review of EP001; 3 · Parallel with: 4

## Progress
- **Phase 5 learning built** (2026-10-17, D39): `lacuna_app/learning.py`, page 「学到的规则」, `scripts/learn_from_hand_edit.py`. Leon's EP001 review read on his PC (read-only): 5 single decisions (kept 3 big content trims, restored 凤凰形态 15.7 s, applied the 秦格雷 suggestion) + 「全部通过」110; 0 routine restores. Too little alone → his hand edit of EP001 added as second evidence source. Rules need his approval before they act. Installed on Leon's PC (main bae39ef) and **validated by Leon 2026-10-17**.

- **Chat asks learned** (2026-10-17, Leon chose 「做」; `docs/decisions/2026-10-17-learn-from-chat-asks.md`): chat log saved per episode (`chat.json`), 「记住：……」 makes a candidate rule at once, after each export one small Claude call turns standing asks in the chat into candidate rules with his sentences. `lacuna_app/chat_learning.py`, tests `tests/app/test_chat_learning.py`, `web/e2e/chat_learning.spec.ts`. Shipped in v2026.10.17.5. Leon 18:57Z asked for a 「记住」 button instead of the typed prefix (PR #63). **Validated by Leon 2026-10-17 19:28Z.**

## How it is built (从审阅里学习 (2026-10-17, D39))
- Evidence: (1) review decisions per first-cut edit, read from each episode's `state.json` + undo history (`lacuna_app/learning.py: decisions`): kept / restored / accepted / declined / added (chat) / untouched, and how (single decision, batch sign-off, none); (2) Leon's own hand edit of the same recording (`scripts/learn_from_hand_edit.py`, S4 alignment) labels every speech edit and finds long passages he cut that the AI left in. Snapshots in `<workspace>/learning/decisions/` (demo episodes ignored).
- Rules (`learn`): protect (AI cuts a kind too much), review (routine kind he restores → goes to review), trust (consequential kind always agreed → auto-apply up to 5 s speech), timid (AI suggestions he cut), missed (cuts he asked for in chat), taste (content passages he cut vs kept, as examples), threshold (confidence calibration). Weights: single 1, batch 0.5, untouched 0.25, hand edit 0.5. Explicit rules win: hand-edit evidence never argues for cutting Pei's stumbles less (R002).
- Approval (D17): every rule starts as a candidate on the page 「学到的规则」(`#/learning`, link in the top bar). Only approved rules act, frozen as approved; new evidence that changes a rule shows as an update to re-approve.
- Consumers: `learning.prompt_rules(workspace)` → text block for the AI first-cut prompt (phase 4); `learning.review_policy(workspace)` → `convert_ops(..., policy=)` / `needs_review(..., kind, host, policy)` (used by `scripts/make_ai_episode.py`).
- Leon (2026-10-17): his EP001_AI review clicks were tests of the app; count the first cut as accepted as delivered (`Learning.accept_as_is`, `learn_from_hand_edit.py --accepted-as-is`) plus his hand edit. He will produce every coming episode in the app and expects learning to iterate slowly.
- EP001 result (cloud preview: v3 ops accepted as is + hand edit): 1 candidate, Leon's content taste (26 cut / 16 kept examples, incl. passages the AI missed). Review threshold unchanged.
- Tests: `tests/app/test_learning.py`, `web/e2e/learning.spec.ts`.

## Page layout: groups + paging (2026-10-17, Leon's ask; #68 + #75 validated by Leon 2026-10-17 20:49Z)
- 「学到的规则」 opens on **待你决定** (candidates + adopted rules with new evidence); **已生效** and **已不采用** are the other two tabs, each with a count. Deciding a rule moves it out of the current tab with a one-line notice and a 「去看看」 link to where it went.
- Each tab pages 10 rules at a time (`web/src/features/learning/Pager.tsx`: prev / numbers with gaps / next, "第 1–10 条，共 23 条"); the pager hides when one page is enough. Paging is client-side: the overview already returns every rule and the cost is recomputing it, not the payload.
- Tests: `web/e2e/learning.spec.ts` (groups, move on decide, 23-rule stubbed paging), `web/e2e/chat_learning.spec.ts`. Screenshots `/mnt/project-files/lacuna/screenshots/learning/`.
- Delete (Leon 2026-10-17 20:22Z): a rejected rule has 「删除」 (two-step confirm). `Learning.decide(id, "delete")` stores state `deleted` in `learning/rules.json`; `overview` skips it, so it never comes back even when re-learned. Also more space between 看例子 and the buttons.

## Open issues
- Chat asks (kind `ask`) feed only the AI first cut, not the chat producer itself; if Leon wants an adopted ask to also steer chat answers, pass `learning.prompt_rules` into the chat scene.
- Content-trim selection is taste: phase 5 turns Leon's cut/kept passages into examples for the first-cut prompt (D39); effect measurable only on a new episode (phase 4).
