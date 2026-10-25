# AI cost cut without Batch: chat caching, Haiku for lessons and track lookups, chat to Sonnet only after a blind test

- Date: 2026-10-25
- Status: CONFIRMED（Leon 2026-10-25「全部同意，都按着你的推荐」，第五批问题 5，甲）
- Supersedes / changes: changes the models in `lacuna_app/lessons.py` and `lacuna_app/library.py`

Target about $3.3 → $2.4 of AI per audio hour without slowing anything a new user sees.
- The producer chat caches its tools + system prompt per show (`cache_control` on the system block; the scene is
  the only varying part). Cost accounting now prices cache writes at 1.25x and reads at 0.1x input.
- Lesson summaries / rule rewrites (`lessons.py`) and track-credit lookups (`library.py`, basic web search, no
  server-side fallback) move to Claude Haiku 5.5. The music-arranging chat stays on Opus.
- The chat stays on Opus until a blind comparison with Sonnet on the host's own past requests
  (`scripts/chat_blind_compare.py`, needs the API key, run on Leon-PC) shows no loss; then `LACUNA_CHAT_MODEL=
  claude-sonnet-5-5` switches it without a release.
- The AI first cut through the Batch API (half price; imports wait usually 10–30 minutes, sometimes hours) is a
  switch, off: 后台 → 系统健康 → AI 省钱 (`lacuna_app/ai_settings.py`). Windows the batch doesn't finish are cut
  the normal way. While it waits, the updater holds deploys (the import counts as busy).

## Blind check on Leon's data (2026-10-25, `scripts/ai_quality_compare.py`, PULSE-013, about $1.75)
- Chat, 15 of Leon's real requests: Opus better 7, tie 8, Sonnet better 0. Sonnet asked back instead of acting
  ("可以", "中间 Pei 的嗯删掉"), twice cut too much, once said it would cut and didn't. **The chat stays on Opus**;
  `LACUNA_CHAT_MODEL` stays unset.
- Lesson summary: Haiku missed two important lessons Sonnet found (Leon's repeated-syllable stutters, Pei's
  run of 嗯 kept to one); 「记住」 rewrites: Haiku hit max_tokens on 2 of 3. **Lessons go back to Sonnet.**
- Credit lookups, 5 tracks: close, but Haiku got one composer's name wrong. Lookups are rare (cost per call is
  small in absolute terms), so with Leon's 「质量优先」 **they go back to Opus.**
- What remains of the cut: chat prompt caching, and the first-cut Batch switch (off).
