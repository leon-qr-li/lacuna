# Nothing Leon says becomes a rule before he confirms LACUNA's reading of it (「记住」 drafts, 本集学到的规则)

- Date: 2026-10-18
- Status: Leon's asks in 首次检测 #9 ("很重要") and #12; details decided by the thread (go-nuts batch)
- Changes: 2026-10-17-learn-from-chat-asks (「记住」 stored his raw words at once; a silent summary ran after export)

## 「记住」 (#9)
- The button, and a chat message starting 记住：/ 记一下 / 帮我记住 / remember:, no longer store anything. One AI
  call (`claude-sonnet-5-5`, forced tool `submit_rule`, ~0.5 ¢) rewrites the ask into a rule (`title`), says how it
  read it (`understood`, "我理解的是……"), writes the first-cut instruction and names an existing ask it repeats.
- The chat shows a card: LACUNA's reading, the rule, 「是否记住这条？」 with 记住这条 / 改一下 / 不用.
  改一下 opens a box (typed or voice) whose text goes back for another rewrite; repeat until it is right.
- 记住这条 = in force at once (state approved on 学到的规则, kind ask): he has just confirmed it, a second 采用
  on another page would be the same question twice. His sentence is kept only as the rule's evidence.
- 不用 stores no rule; the draft stays on file (habits are never deleted).
- No API key / the call fails: the card says so and shows his words for him to confirm or replace via 改一下.

## 本集学到的规则 (#12)
- A step of the episode flow between 整集试听 and 配乐 (`web/src/features/lessons/`, tab order 20). Opening it the
  first time starts the summary; no extra click. Skippable: 下一步：配乐 is always there and nothing waits on it.
- One AI call (forced tool `submit_lessons`, ~2–4 ¢) gets the episode's whole chat log (what he said, the reply,
  approved or not), his review decisions (kept / restored / accepted / declined / added, with words and how he
  decided) and the existing rules with their state. Each lesson: rule, first-cut instruction, why (evidence in
  words), relation new / reinforce / conflict with the related rule, and the chat turns and edits it cites. A
  lesson citing nothing real is dropped; an unknown related rule makes it "new".
- Per lesson: 采用 / 直接改 (type the wording) / 跟 LACUNA 说怎么改 (typed or voice, same rewrite as 改一下) /
  跳过 (→ 已处理, 重新考虑 brings it back). Adopted = in force. Withdrawing stays on 学到的规则 only.
- Adoption: reinforce of a chat ask keeps its wording and adds the evidence; conflict with (or an edited
  reinforce of) a chat ask stores the new wording under the same rule (habits iterate); reinforce of a learned
  review rule approves that rule; a conflict with a review rule adds a new ask whose instruction says it
  overrides the old one; everything else is a new ask.
- Re-run (「重新总结」, flagged when chat or review changed since): undecided lessons are replaced, decided ones
  kept and shown to the AI as already reviewed (and never proposed again).
- The silent after-export summary (`ChatLearner`) is removed: the export no longer calls the AI for learning.
  Asks it made earlier stay as they were.

## Storage
`<workspace>/learning/lessons/<episode>.json` (drafts, summary state, lessons with history of every change),
next to the other learning files, so it outlives the episode folder. Confirmed rules go to
`learning/asks/<episode>.json` (`ChatAsks.put`) and `learning/rules.json` as before.
