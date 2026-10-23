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

## Polish round (2026-10-22, second PR on the same branch)
Decision: `docs/decisions/2026-10-22-bubble-tour.md`.
- 声音 page design A (`features/levels/LevelsView.tsx`): a card per host with meter, before/after waves (first 30 s),
  −1 / slider / +1, 用建议值, clipping per card; 对比这里：原始 / 调整后 (`GET …/levels/ab`).
- 配乐 page design B (`features/library/MusicLibrary.tsx`, `MusicCard.tsx`, `music-b.css`): library on the left
  (▶, 放到 ▾), one open card with a volume curve whose white dots drag (or arrow keys), sliders with numbers and
  − / +, 更多设置 with ±5 s, 用在 scope + 设为默认片头片尾.
- 导出 page (`components/ExportPanel.tsx`, `features/export/Summary.tsx`): formats / start / download left, this
  episode + platform standard right.
- Review page: no empty space under the list.
- Sample v2 (`lacuna_app/sample.py`): 2:10 raw, five first-cut spots (three to review), the actor lines, 「等一下
  我喝口水」, a cough under the other host, host 0 about 9.5 dB louder, three CC0 tracks in its library
  (`lacuna_app/sample_music/`, licenses.json with source sha256).
- Bubble tour replaces the coach panel (`web/src/features/tour/`): 9 chapters, 57 bubbles, locked mask, dashed
  targets on the timeline, position kept on the server (`onboarding.tour`), before / after at the end. The two
  sentences it fills in are answered by `sample.tour_chat` / `sample.tour_music_chat` without the AI;
  `GET …/tour/raw` and `GET …/tour/marks` (`routes/tour.py`).
- Tests: `tests/app/test_onboarding.py` (tour), `web/e2e/tour.spec.ts` (the whole tour), `onboarding.spec.ts`,
  `levels.spec.ts`, `music_b.spec.ts`, `review_gap.spec.ts`.

- Invite email 6 steps: copy B 「专业名词式」 (Leon 2026-10-23) in `invite_mail.steps()`; English kept to one
  line per step in the two-column layout ("Music & loudness normalization", "Multi-platform export").

- Tour fixes from Leon's 验收 (2026-10-23): every step change pauses all audio, and the pill shows 「⏸ 暂停播放」
  while anything plays; 跳过教程 is gone from the bubbles, a quiet × on the pill asks 「还剩 N 步，大约 M 分钟」
  (继续教程 primary) and leaving keeps the place (`onboarding.tour = "~step"`, pill 「继续示例教程」);
  timeline steps call `showOnTimeline` (EditLanes, zooms out when needed); listening steps take 知道了 too;
  new bubble rrest on 「剩下的全部保留」 while it still shows. Review keys: K always the cut (re-applies a
  restored edit), R always the original words.

## Open
- Sample audio: Leon asked for a synthetic two-voice sample first (stock voices, not cloned); goes in only after he listens. Real recordings (Leon + Pei, zh + en) still the end goal → run ASR + first cut, check by hand, bump `sample.VERSION`.
- Chat cap in the sample show (~20 messages) and audio-hour metering skipping `sample` shows: batch 5.
- Usage line on welcome / import form ("本月已用 …"): needs batch 5 metering.
