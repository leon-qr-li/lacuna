# Transcripts are proofread against the show's own names, by a text-only AI pass after recognition

- Date: 2026-10-20
- Status: Claude 技术决策 (Leon asked for it: 文字稿要按项目设置自动纠错, 2026-10-20 18:31Z)
- Supersedes / changes: —

The local recognisers can't be told the show's names: sherpa-onnx's Paraformer (zh) takes no hot words
(only transducer models do, with modified beam search; SeACo-Paraformer is a different model in
FunASR), so 《洛城二三事》 came out as 洛城二三世, Leon / Pei as 利奥 / 配, the series PULSE as "pose".
Swapping the recogniser was rejected (big, risky, Chinese accuracy measured on the current one).

Instead, right after recognition and before the AI first cut, one text-only request per ~6,000
characters (Sonnet 5.5, structured output) gets the transcript lines plus the show's reference terms
(show name, hosts, albums, project-settings terms, names corrected before in names.json, Latin names in
the episode title) and answers {line, wrong, right}. The code applies a fix only if `right` is one of
the terms and `wrong` quotes whole words of that line; it changes word text only (a term heard as
several words becomes one word over their times), so audio, edits and timing never change and no word
is added. names.json corrections apply without the model. Any failure leaves the text as heard.
Episodes imported before get the same pass from the 「校对专有名词」 chip on 文字稿剪辑 (the first pass
keeps `transcript.before_fix.json`). Cost ≈ $0.02–0.05 per hour of audio. Off: `LACUNA_TRANSCRIPT_FIX=off`.
Code: `lacuna_app/transcript_fix.py`, `routes/transcript_fix.py`, `web/src/features/transcript-fix/`.
