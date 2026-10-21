# Next build batch (2026-10-21)

Thread 下一批. Branch `claude/next-batch-h506ff`, one integration PR with the `staging` label.

## State (2026-10-21)
All nine picked items built, with tests:
1. 整集试听 timeline menu — decision `listen-timeline-menu`; `web/src/features/manual/LaneMenu.tsx`, EditLanes;
   minimap removed. e2e manual.spec, workbench.spec.
2. 设置 side nav — decision `settings-side-nav`; `web/src/features/settings/SettingsView.tsx`. e2e settings.spec.
3. Invite email 「夜航信笺」 — decision `invite-email-design`; `lacuna_app/invite_mail.py`. tests test_auth_invites_2fa, e2e auth.spec.
4. 新建项目 dialog centred (portal to body). e2e spaces.spec.
5. Max four hosts / tracks — decision `four-hosts-max`. tests test_show, test_import; e2e show.spec.
6. Project picture / colour / archive / delete — decision `projects-archive-delete`. tests
   tests/app/test_spaces_archive.py, e2e project_archive.spec.ts.
7. Transcript proofreading audio-first + per-project 专有名词 — decision `transcript-audio-first`. tests test_transcript_fix.
8. Episode card actions as a footer row (no overlap with the title). e2e albums.spec.
9. Top bar without Undo/Redo/Export, toast 撤销 — decision `top-bar-no-undo`. e2e undo.ts helper.

## Next
- Leon's E2E on staging, then squash merge. Findings go to the next batch.
- Still on the pre-launch list: the 4-host editing test with real audio.
