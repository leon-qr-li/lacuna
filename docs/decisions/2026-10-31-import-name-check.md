# 导入时核对专有名词 (proper-noun check at import) — 2026-10-31

Leon liked the show notes' 「专有名词核对」 and asked for it on the transcript at import, on by default, before
审阅, so 审阅 / 整集试听 (and the AI first cut) already read the right names and the show notes need not ask again.

- `lacuna_app/name_check.py`: after the show's own names are proofread (`transcript_fix.py`, decision
  `transcript-terms`), one more text-only pass asks the top model (`claude-opus-5-5`, same as the show notes and
  chat; quality first) for film titles, people, places and other proper nouns the recogniser mis-heard, with
  what it is (`why`). Chunks of ~9000 characters, 4 in parallel.
- The same safety rules as `transcript-terms` / `transcript-audio-first`: `wrong` must be whole words of that line
  and must sound like `right` (`sounds_alike`); only word text changes, every time stays, no word is added;
  any failure leaves the text as heard and never fails or delays an import.
- Applied without asking. The episode lists them (`<episode>/name_check.json`): the chip 「专有名词已核对 N」 on
  逐字稿剪辑 opens heard → written, what it is, 「听一下」 and 「改回原样」. Put back pairs go to
  `<workspace>/name_keep.json`: later imports and the show notes' 专有名词核对 leave them alone.
- On by default; 项目设置 → 基本信息 → 「导入时自动核对片名、人名等专有名词」 (`show.json` `name_check`)
  turns it off; `LACUNA_NAME_CHECK=off` for the whole server.
- Only new imports. Episodes imported before are not re-checked (cost, and Leon's episodes stay as they are).
- Cost (estimate): one Opus pass over the transcript, about $0.30–0.60 per audio hour; logged as `name_check`
  in `ai_usage.jsonl`.

Code: `lacuna_app/name_check.py`, `lacuna_app/prompts/name_check.txt`, `lacuna_app/routes/name_check.py`,
`web/src/features/name-check/`; tests `tests/app/test_name_check.py`, `web/e2e/name_check.spec.ts`.
