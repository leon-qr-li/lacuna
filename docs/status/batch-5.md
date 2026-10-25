# Batch 5: pre-beta hardening (上线前加固)

Branch `claude/project-thread-qslvgt`, one integration PR. Leon approved all 7 decisions on 2026-10-25 00:07Z
(typed 「全部同意，都按着你的推荐」, includes the security change #7); decision page
https://claude.ai/artifact/3foGFupGircLvbfofN17SE.

## Done (code + tests)
- Uploads + server-wide import queue — decision `2026-10-24-upload-and-queue`. `import_queue.py`,
  `upload_parts.py`, `web/src/features/import/draft.ts`, `UploadBadge.tsx`.
- Audio-hour metering, admin usage column, 设置 → 套餐与用量 bar — decision `2026-10-24-hour-metering`. `quota.py`,
  `routes/quota.py`, `web/src/admin/pages/Hours.tsx`, `web/src/features/plans/PlanCard.tsx`.
- Cold storage (R2) and audio restore on open — decision `2026-10-25-audio-cold-storage`. `cold.py`, `r2.py`,
  `routes/cold.py`, `web/src/features/cold/`, E2E `web/e2e/cold_audio.spec.ts`.
- Retention: latest export only (on), raw tracks 12 months + reminder (off in beta) — decision
  `2026-10-25-audio-retention`. `retention.py`, admin 系统健康 → 存储与保留 (`web/src/admin/pages/Storage.tsx`).
- Infra: audio bucket + tokens, data disk 100 GB, staging hard-links audio, public `/api/version` withdrawn,
  deploy check with an Access service token — decision `2026-10-25-withdraw-public-version`. `deploy/provision.py`,
  `deploy/ci.py`, `deploy/host/*`, workflows.
- Capacity alerts — decision `2026-10-25-capacity-alerts`. `capacity.py`, admin home (`Capacity.tsx`), digest.
- AI cost cut — decision `2026-10-25-ai-cost-cut`. Chat prompt caching (`editor.py`), Haiku for `lessons.py` and
  `library.py` credit lookups, first-cut Batch switch off (`ai_settings.py`, admin 系统健康 → AI 省钱,
  `web/src/admin/pages/AiCost.tsx`), `scripts/chat_blind_compare.py`.

## Going live (in order; nothing here is done until the PR is merged)
1. Merge → Deploy. wait-live uses a per-run Access token until step 3.
2. Provision `apply`: deletes the version door, makes bucket `lacuna-audio` + 2 tokens, grows the volume to 100 GB.
3. Provision `deploy-token` with the repo's Actions public key, then store the sealed values as secrets
   `CF_DEPLOY_CLIENT_ID` / `CF_DEPLOY_CLIENT_SECRET` (`gh` on Leon-PC; deploy/README.md).
4. Provision `recreate` after Leon types 「重建服务器」: the app gets `LACUNA_AUDIO_*`, bootstrap runs `resize2fs`.
   Not during a big upload or data op.
5. Check: admin 系统健康 shows 「云存储已接通」; 14 days later old episodes start moving.

## Open
- Model quality check done 2026-10-25 on Leon-PC (`scripts/ai_quality_compare.py`): chat stays Opus, lessons back
  to Sonnet, credit lookups back to Opus (decision `2026-10-25-ai-cost-cut`, last section).
- Done 2026-10-25: merged (#203), deployed, Provision apply, deploy-token secrets stored. Left: recreate (typed
  「重建服务器」).
- Console monthly spend cap: Leon sets it in the Console.
- Stress test before launch (beta-launch-todo); not in this batch.
