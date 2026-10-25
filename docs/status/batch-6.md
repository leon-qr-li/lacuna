# Batch 6: terms + privacy, patrol and support design, storage stress test

Thread 「第六批:条款与巡检客服」, branch `claude/project-thread-9e2dfv`, one integration PR. Leon said 「做」 on
2026-10-25 04:19Z to the coordinator's proposal: (1) build the ToS + privacy draft with the sign-up tick, (2) DESIGN
ONLY the admin patrol + daily digest and the in-app 「LACUNA 客服」, (3) stress-test the cloud audio storage.

## Done (code + tests)
- 用户条款 / 隐私政策 draft, zh + en, at `/legal/terms` and `/legal/privacy`; tick to agree at sign-up (first
  account and invites); accounts without the current version agree once after signing in (cloud). Decision
  `2026-10-25-terms-and-privacy`. Code: `lacuna_app/legal.py`, `lacuna_app/routes/legal.py`, `auth.py` (register
  records it, status reports it), `web/src/features/legal/`, `AuthScreen.tsx`, `AuthGate.tsx`, `AccountCard.tsx`.
  Tests: `tests/app/test_legal.py`, `web/e2e/legal.spec.ts`; sign-up specs tick the box.

## Open
- Placeholders in the documents (entity, law, DMCA agent, emails…): fill with the lawyer before public launch.
- Patrol / digest and 「LACUNA 客服」: designed, waiting for Leon's decisions (巡-1…7, 客-1…10, recommendations in
  the summary page https://claude.ai/artifact/QjVV3kgkHwXYJJoDXEjigS; 17 mockups in the canvas
  https://claude.ai/artifact/KHsVNkGtykTkzkuV3Y1GyP). No code until he says build. Patrol = scheduled routine on
  Leon's subscription reading a read-only snapshot endpoint (new read-only token = security change, needs Leon's typed
  OK); server's rule digest (`admin_digest.py`) stays as fallback. Support = API key, Opus, ~$0.04/message,
  ~$30/month in beta, $60 cap, escalation list fixed.
- Real DigitalOcean ↔ R2 restore speed not measured yet (measure on the first real 14-day-old episode).

## Leon 2026-10-25 06:34Z: AI support moved to AFTER BETA
「AI 客服的大功能，留在 beta 上线之后，等人数上来之后…把开关给我关死了，甚至不要让我开开的选项」. During beta Leon
handles all support by hand (in-app 反馈 + admin). The AI support agent is NOT built and the admin gets NO switch for
it; Claude builds it only when Leon raises it again after beta, when user numbers grow. The design (canvas boards
S1–S8, A1–A2, decisions 客-1…9) stays as the starting point. The 17 decisions are all deferred; the patrol design
(巡-1…7) waits for Leon too. Nothing in the product calls an AI for support.

## Storage stress test (2026-10-25)
`scripts/stress_cold_storage.py` runs freeze / thaw / multipart / GC against a local S3-compatible server with
injected faults (503, dropped connections, flipped bytes, disk full). Results: 0 lost, 0 corrupted in every run.
24 episodes × 3 × 24 MB froze in 27 s through 10 × 503 + 3 drops; all 24 thawed at once in 4.7 s through 6 bad
responses; episodes opened mid-freeze kept their audio; ENOSPC left no partial file; 1.3 GB multipart under 10 %
faults left no open upload; GC removed only unreferenced objects older than 7 days; at 4× faults one freeze and one
thaw failed safely and succeeded on the next try. Hashing ~340 MB/s (≈ 6 s per 2 GB episode). Loopback speed only.
