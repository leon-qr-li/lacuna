# Batch 11: full regression again (code freeze)

Thread 「第十一批：再跑一遍完整回归」 (Leon 2026-10-26: 「再跑一遍 full regression」). The 333 cases of batch 8
(case page https://claude.ai/artifact/GPtn1TkZHGzoy8tEqnd4Gg) run again from the start, with #223–#225 covered.

## Runs (2026-10-26)
- pytest 894 passed / 17 skipped (real-model ASR, EP001 audio, host scripts); `npm run build` (types, i18n, brand).
- E2E 151 / 153 in one local run; the two that failed (`batch7 B13`, `import` new-show task card) pass on their own:
  both depend on what earlier specs left on the shared server in a single unsharded run (CI shards them).
- Visual sweep on local servers, zh / en × dark / light × 1440 / 1024 / 390, with an automatic check (sideways
  scroll, clipped text, text off screen, console errors): a cloud-mode site with accounts (scripts/loadtest/make_site.py,
  2FA + terms set up through the API) for the main site (27 pages, 324 shots); signed out on a non-loopback address
  (sign-in, forgot password, request access, invite sign-up, terms, privacy: 72); the terms gate (12); the admin on
  demo data (12 pages, 144). No layout problem found; the only console noise is the known 401 of `/api/site/notice`
  before sign-in. The admin invite mail rendered zh / en at 700 and 390.
- Role probe: every changing route of the main site fired as a 只听 member, as the admin of an archived show and as a
  stranger pointing the show cookie at someone else's show: all refused (the stranger lands in their own show).

## Fixes (this PR)
- EG-12: an export took the music as it was when its thread started mixing, so music changed right after 开始导出
  could end up in it while the record said otherwise. The export now holds the placements read when it starts
  (`Exporter.start`, `EpisodeMusic.export_key(placements)`); a change made meanwhile marks it out of date.
- AU-28: 节目设置 → 协作者 listed emails only; the people list now carries each member's name, shown with the email
  under it.

## Waiting on Leon (security, needs his typed words)
- Signed-in answers still carry server folder paths in the cloud: `/api/health` (`workspace`), `/api/library`
  (`folder`), export result `folder`, publish `notes_path`, poster `cover.folder`, 喜马拉雅 `dir`, save-cover `path`.
  The screens don't show them in the cloud. Proposed: leave them out in the cloud (import's own track paths stay).

## Next action
Merge the fix PR → deploy. Then Leon's week of testing from the case page.
