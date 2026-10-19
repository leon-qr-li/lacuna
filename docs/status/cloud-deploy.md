# Cloud deployment (上云部署)

Thread「上云部署」. Decision: `docs/decisions/2026-10-19-cloud-deploy.md`.

## State (2026-10-19)
- PR 1 (this): cloud mode in the app (`lacuna_app/cloud.py`, `routes/cloud.py`; on only with `LACUNA_CLOUD=1`):
  Cloudflare Access token checked on every request except the container's loopback; desktop-only actions
  404 (update/restart, API-key/Resend-key saving, open folder); pre-sign-in `/api/app` + `/api/health` show
  only the version; imports read only uploaded tracks. `--host` accepts non-loopback only in cloud mode.
  `Dockerfile` + `deploy/smoke_container.sh`, built and smoke-tested by `.github/workflows/cloud.yml`.
  Tests: `tests/app/test_cloud.py`.
- Next: provisioning (droplet, volume, firewall, registry, tunnel, Access, R2) as an idempotent script run by a
  manual workflow; droplet updater + backups; deploy-on-merge workflow; chunked upload (Cloudflare's 100 MB
  request limit).
- Waiting on Leon: DigitalOcean account + token, Cloudflare Zero Trust team + R2 + API token, six GitHub
  secrets (DIGITALOCEAN_TOKEN, CLOUDFLARE_API_TOKEN, ACCESS_EMAILS, BACKUP_PASSWORD, ANTHROPIC_API_KEY,
  RESEND_API_KEY). Asked 2026-10-19 02:4xZ.

## Agreed with 「账号与权限」
They own auth.py / routes/auth.py, invites, 2FA, roles, per-user data. They set `secure=True` on the session
cookie in cloud mode and call `cloud.access_allow(email)` / `access_revoke(email)` when invites change.
