# 一键修复曲名和作者 (credit fix)

Date: 2026-10-30 · Decided by Leon (design page https://claude.ai/artifact/6zGqMSTwsyHYszw3ukkz5p, direction A)

## Context
Leon uploads an episode's music on that episode's 配乐 page (it belongs to 只这一集 by default); the library is
mainly for shared intros / outros. LACUNA's title lookup only existed per track in the library, after writing a
note. He wants one button that fixes every title and artist of the episode's music, from one sentence about where
the music comes from.

## Decision
- 「一键修复曲名」 on the 配乐 page (library list head + BGM 署名 card) covers the music only that episode has;
  the same button on the library page covers the shared music (whole show or an album). Shared music is never
  changed from an episode's page.
- A popup takes an optional sentence ("全是《午夜凶铃》原声"). LACUNA (Opus + web search, same model as the single
  lookup) gets text only: the sentence, file names, embedded tags, durations, notes. It matches files to a
  soundtrack's track list by duration. It never hears audio; no fingerprint service (direction C declined).
- Results wait in a list (direction A): confident ones start ticked, two-candidate ones offer 换成, unknown ones
  can't be ticked, each can be edited. Nothing changes before 采用; ticked ones become confirmed.
- Confirmed credits are skipped unless 已确认的也重新查 is ticked. No automatic lookup after an upload; the button
  is outlined in orange while the music has unconfirmed titles.
- The music page list shows 「作者 · 出处」 under each title (composer of a score, performer of a song).
- The lookup runs in the background (it can outlast a request); its result is kept in
  `library/.credit_fix/<key>.json` until applied or dropped.

## Code
`lacuna_app/credit_fix.py`, `lacuna_app/routes/credit_fix.py`, `web/src/features/credit-fix/`,
tests `tests/app/test_credit_fix.py`, `web/e2e/credit_fix.spec.ts`.
