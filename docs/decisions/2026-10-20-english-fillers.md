# English um / uh: shown in the transcript, removed in one step

- Date: 2026-10-20
- Status: Claude 技术与界面决策 (Leon 2026-10-20 15:14Z picked "英文口头禅检测" and said it does not need him); Leon checks it on staging
- Builds on: `english-engine` (detection of dropped um / uh), `manual-editing` (transcript card, manual edits)

Until now the um / uh that English recognisers drop were found at import (`features.build` `hear`) but only handed
to the AI first cut as `~filler` lines; the AI keeps a natural residue, and the person could neither see nor
remove the rest.

- **Into the transcript.** At import the detected fillers become words of their host's transcript track
  (`fillers.merge`, text as heard: "uh", "um"), so 文字稿剪辑, the chat, the edit lists and learning all see them,
  and one the AI cut shows struck through. English episodes imported earlier are merged once from their import's
  `features.json` the first time their fillers are listed (`fillers.backfill`).
- **去掉 um / uh** (chip on 文字稿剪辑, English episodes only): shows how many um / uh are still heard; its panel
  lists them per host (untick a host to keep theirs), 听下一个 plays from just before the next one, and
  去掉 N 个 removes them all as ONE undoable step (`去掉 um / uh（N 处）`). Fillers the recogniser wrote ("Um,")
  count too (`features.is_filler`: um, uh, er, erm, ah …; never "mm" / "hmm" / "uh-huh").
- **Each filler is its own edit** (source `manual`, category `filler`, applied + approved), so a click on one struck
  word brings back only that one, and the lists show them as 手动剪辑.
- **How it is cut:** cut from every track and the timeline closes up, unless another track sounds there (words or
  audio above -38 dBFS RMS): then only that host is silenced, filled with their room tone. Edges get 20 ms either
  side (never into the host's neighbouring words) and snap to the quietest sample within 60 ms, like a manual cut.
- The AI first cut is unchanged (it still keeps a natural residue); the button is the person's choice to go further.
  Chinese 嗯 / 呃 are not included (often a backchannel meaning "yes"); revisit if asked.
