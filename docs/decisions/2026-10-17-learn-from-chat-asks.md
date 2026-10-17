# Long-term asks said in the chat become candidate rules (saved chat log, 记住, after-export summary)

- Date: 2026-10-17
- Status: Leon 决定 (decision card 17:17Z, 「做」: "要不要让对话框里你说的长期要求也学成规则？")
- Changes: D39 (learning only read edit outcomes; chat wording was in memory only and lost)

- The AI producer chat log is saved with the episode: `<episode>/chat.json` (store: atomic write + .bak), what
  Leon said, where, the producer's reply and whether he approved. A restart keeps the chat history.
- A 「记住」 button next to 发送 (Leon 18:57Z: typing the prefix is error-prone) records what is typed as is
  (`POST /api/episodes/<id>/remember`, `features/learning/RememberButton.tsx`). The typed prefix 「记住：……」 (also 记一下 / 帮我记住 / remember:) in the chat makes a candidate rule at once, in his own words,
  with no AI call.
- After each export (Exporter `on_done` hook, in the background, never affects the export): one Claude call
  (`claude-sonnet-5-5`, forced tool `submit_long_term_asks`, ~1–2 ¢) reads the chat turns since the last summary
  (text only) and returns standing preferences, each citing the turns it came from; an ask with no cited turn
  is dropped. Known asks are shown to it so a repeat in a later episode reuses the id and the quotes add up.
  No key → turns stay pending for the next export. Usage logged as `chat_learning`.
- Storage `<workspace>/learning/asks/<episode>.json`; they show on 学到的规则 as kind `ask` (「你说过的」) with
  his sentences as examples. Like every learned rule (D17) they act only after 采用, then go into the first-cut
  prompt via `learning.prompt_rules`.
