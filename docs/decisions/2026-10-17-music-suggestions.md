# Music is placed by its use, changed by talking, and always heard as a suggestion before it counts

- Date: 2026-10-17
- Status: Claude 技术决策 (Leon's ask, relayed 15:51Z: "我怎么 review 他加这个音乐？我怎么给他提意见他加了哪秒？")
- Supersedes / changes: D45, D48 (open issues "chat cannot place music", "stale hint ignores music")

- 「按用途自动放好」 on the 配乐 tab: intro / outro from the series rule or the newest asset of that use; the
  interlude at a pause at a publish-pack chapter start, else the longest pause between 20 % and 90 % of the
  episode (other good pauses, at least 60 s apart, offered as 「换个位置」). 聊天背景音 / 对白 / trailer are only
  mentioned: where they go is Leon's call.
- 「跟 Claude 说配乐怎么改」: Claude (text only: placements, library names / uses / notes, chapters, transcript
  near each placement and near the longest pauses; never audio) answers with add / move / set / remove
  actions in final-mix seconds; positions snap to the nearest pause (±4 s). Model `claude-opus-5-5`, effort
  low, forced tool `arrange_music`; usage logged as `music_chat`.
- Both produce one **suggestion** (`music.json["draft"]`, a full alternative placement list). Leon hears each
  change (「试听」 renders the mix with the suggestion), then 「采用」 or 「不要」. Only 采用 changes the music;
  a suggestion made before a later edit is stale and can't be accepted. Export never sees a suggestion.
- Each anchored placement shows its final-mix position, editable, with 「早 1 秒 / 晚 1 秒」 (exact, no snapping).
- Exports record `music_version` (applied placements + their assets' levels); the export popover and the
  上传喜马拉雅 page say the export is stale when the music changed after it.

Changed by: `2026-10-18-ai-called-lacuna` — the chat box reads 「跟 LACUNA 说配乐怎么改」 (code and model unchanged).
