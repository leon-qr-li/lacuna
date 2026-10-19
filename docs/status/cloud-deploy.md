# Cloud deployment (上云部署)

Thread「上云部署」. Decision: `docs/decisions/2026-10-19-cloud-deploy.md`.

## State (2026-10-19)
- PR #118 (merged 2026-10-19): cloud mode in the app (`lacuna_app/cloud.py`, `routes/cloud.py`; on only with `LACUNA_CLOUD=1`):
  Cloudflare Access token checked on every request except the container's loopback; desktop-only actions
  404 (update/restart, API-key/Resend-key saving, open folder); pre-sign-in `/api/app` + `/api/health` show
  only the version; imports read only uploaded tracks. `--host` accepts non-loopback only in cloud mode.
  `Dockerfile` + `deploy/smoke_container.sh`, built and smoke-tested by `.github/workflows/cloud.yml`.
  Tests: `tests/app/test_cloud.py`.
  Also: macOS CI installs ffmpeg with Homebrew (setup-ffmpeg's macOS ARM lookup broke upstream 2026-10-19).
- PR 2: `deploy/provision.py` (idempotent; DO registry/volume/firewall/droplet, CF tunnel/DNS/Access/R2, two
  narrow server tokens), `deploy/host/*` (bootstrap, updater, backup, metadata block), `deploy/ci.py`,
  workflows Provision / Deploy / Backup check, runbook `deploy/README.md`. Tests: `tests/test_provision.py`,
  `tests/test_deploy_host.py` (fake docker).
- PR #121: cloud 设置 page (no manual update, no key field, no 这台电脑); Provision picks an available
  4 vCPU / 8 GB size (sfo3 refused `s-4vcpu-8gb`, server runs `s-4vcpu-8gb-intel`); `cloud.access_email()` /
  `cloud.owner_email()` (`LACUNA_OWNER_EMAIL` = first ACCESS_EMAILS entry) so the owner's first sign-up needs
  no setup code (the server has no shell; accounts thread #123 uses it).
- PR #124: container registry on the basic plan ($5/month; starter's 500 MB is smaller than the image).
- LIVE 2026-10-19 04:07Z: https://lacunastudio.app, deployed by the Deploy workflow (wait-live passed).
  Leon signs in first (Access email code → password → TOTP → recovery codes). Only Leon is on the invite list.
- Big files in pieces: `lacuna_app/upload_parts.py` + `routes/upload_parts.py`; the browser sends files over
  48 MB as 32 MB pieces (`web/src/features/upload-parts/pieces.ts`), then the import-track / library upload
  endpoint takes `part=<id>`. Tests: `tests/app/test_upload_parts.py`.
- Moving the desktop workspace (PR #127): 设置 →「从电脑搬过来」, a one-time browser upload of
  LACUNA_Workspace that rewrote the desktop's absolute paths. Removed after use (see below); it's in git history.
- Staging (decision `docs/decisions/2026-10-19-staging-site.md`): preview.lacunastudio.app, second container
  on the same server, data `/data/preview` re-copied from the real workspace for each new version; PR label
  `staging` + workflow **Staging**. Needs one Provision `recreate` to reach the server (host scripts and
  env files only arrive with cloud-init). Tests: `tests/test_provision.py`, `tests/test_deploy_host.py`,
  `tests/app/test_staging.py`, `web/e2e/staging.spec.ts`.
- Staging live 2026-10-19 06:57Z (Provision apply + recreate; Deploy run 11 passed wait-live on the new
  server). Release flow (Leon 06:55Z): thread deploys its PR to staging, Leon says 通过 in chat, the thread
  merges = production. Leon presses no buttons.
- Migration DONE 2026-10-19 07:18Z: Leon uploaded his workspace (≈5.4 GB) via 设置 →「从电脑搬过来」 and
  checked the data on the site. One stall at 45% (a piece request hung without error; stop, reload, start
  again resumed). Then the feature was removed (Leon: cloud-only from now on). Next: retire the desktop app.
- Staging workflow (PR #130): deploy tooling comes from main, only the image is built from the PR commit
  (a PR branched before #128 ran an old `deploy/ci.py`).
- Never ask Leon before moving real data to the cloud (Leon 06:58Z).
- Gotcha: Deploy and Provision share the concurrency group `deploy`; a Deploy waiting for a server that
  doesn't exist yet blocks Provision until it is cancelled.

## Agreed with 「账号与权限」
They own auth.py / routes/auth.py, invites, 2FA, roles, per-user data. They set `secure=True` on the session
cookie in cloud mode and call `cloud.access_allow(email)` / `access_revoke(email)` when invites change.
- 2026-10-19 15:22Z Deploy run 16 failed: the DigitalOcean registry answered 401 to credentials issued
  seconds earlier (also Deploy run 13 at 07:22Z); a re-run passes. Deploy and Staging now log in again and
  push once more when the first push fails, and a failed Staging deploy comments on its PR (wakes the thread
  watching it). An hourly scheduled check in the 「上云部署」 thread looks at Deploy / Staging / Backup check
  runs and fixes failures without waiting for Leon.
- 2026-10-19 ~16:00–17:00Z every push failed with 401: the real cause of the "registry 401" failures was the
  registry's garbage collection, which Deploy started after every release (`ci.py registry-gc`). While it
  runs the registry is read-only and refuses pushes with 401; back-to-back merges kept it busy. Now Deploy
  only deletes old tags; the daily Backup check starts the collection (`ci.py registry-collect`), and every
  push first waits for a running collection (`ci.py wait_gc`, up to 45 min).
