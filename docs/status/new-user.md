# New-user experience batch — status

Decision: `docs/decisions/2026-10-22-new-user-experience.md`. One integration PR on `claude/project-thread-iltayg`.

## Done (2026-10-22)
- Quick fixes: show language follows the UI, cloud wording (LACUNA 的服务器), server paths / folder buttons hidden in
  the cloud, 喜马拉雅 tabs per show, no AI cost amount, music empty state, settings text, inviter's name, request
  page promise, trial invite hint, sole admin can't be removed (H4), finished import cards go (H8), export notes
  edits not looked at (G5).
- Invite email compact design A with the plan card; name at sign-up and in 账号.
- 「新成员需站长批准」 switch + 搭档申请 (`routes/new_members.py`, `routes/auth_requests.py`).
- Application form asks about separate tracks.
- Platform multi-select (`show.py` PLATFORMS).
- Review page version A (`components/ReviewView.tsx`, `ReviewView.css`).
- Welcome page, 入门清单, top-bar tag, coach panel, collaborator short version, 设置 → 通用 card
  (`web/src/features/onboarding/`, `routes/onboarding.py`).
- Sample show (`lacuna_app/sample.py`): placeholder recording, shared read-only audio, reset / delete.
- 节目资料卡 + import hint (`web/src/features/show/ProfileCard.tsx`).
- Dialogue outline for Leon and Pei: https://claude.ai/artifact/H14QxsyixJ59cthFbdNSs5
- Tests: `tests/app/test_onboarding.py`, `tests/app/test_new_members.py`, `web/e2e/onboarding.spec.ts`.

## Open
- Real sample recordings (Leon + Pei, zh + en) → run ASR + first cut, check by hand, bump `sample.VERSION`.
- Sample music files: download the 5 CC0 tracks (container can't reach FMA), keep license URL + date per track,
  preload intro / outro / bed into the sample show's library.
- Chat cap in the sample show (~20 messages) and audio-hour metering skipping `sample` shows: batch 5.
- Usage line on welcome / import form ("本月已用 …"): needs batch 5 metering.
