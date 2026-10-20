# Cloud runbook (lacunastudio.app)

Decision: `docs/decisions/2026-10-19-cloud-deploy.md`. Status: `docs/status/cloud-deploy.md`.

## Pieces
| What | Where |
|---|---|
| App image | `Dockerfile`; smoke test `deploy/smoke_container.sh` (workflow **Cloud image**, on PRs) |
| Ship on green main | workflow **Deploy** → DO registry `:main` → server updater swaps it in, `deploy/ci.py wait-live` confirms via the public `/api/version` (version only; decision `public-version-check`) |
| Create / change infra | workflow **Provision** (`plan` / `apply` / `recreate`) → `deploy/provision.py` |
| Server first boot | cloud-init built by `provision.py` from `deploy/host/*` (`lacuna-bootstrap`) |
| Server updater | `deploy/host/lacuna-update` (timer, every minute; waits for jobs; rolls back) |
| Staging | PR label `staging` → workflow **Staging** → registry `:preview` → `lacuna-update-preview` (fresh copy of the workspace in `/data/preview`, then the new version) → https://preview.lacunastudio.app |
| Backups | `deploy/host/lacuna-backup` (nightly restic → R2); workflow **Backup check** (daily: age, restore drill; Sundays: volume snapshot) |

GitHub secrets: `DIGITALOCEAN_TOKEN`, `CLOUDFLARE_API_TOKEN`, `ACCESS_EMAILS`, `BACKUP_PASSWORD`,
`ANTHROPIC_API_KEY`, `RESEND_API_KEY`. Workflow logs are public (public repo): scripts mask every secret
and print no emails or IPs.

## Common tasks
- **First setup**: Provision `plan`, then `apply`, then run **Deploy** by hand once (later merges deploy themselves).
- **Change a secret / a host script**: update it, then Provision `recreate` (a few minutes down; data volume kept).
- **Let someone in**: the app's invites add the email to the Access group; `ACCESS_EMAILS` only seeds it.
- **A deploy didn't go live**: the Deploy run says so after 30 min. Either a long import/export was running
  (it goes live when that finishes) or the new version failed its health check and the server went back
  to the previous one (`/var/lib/lacuna/deploy.json` + `failed-start.log` on the server). Fix forward with a PR.
- **Server broken / lost**: Provision `recreate` builds a new one on the same data volume.
- **Data volume lost**: restore the newest restic snapshot (below) onto a fresh volume, or restore the
  newest DO volume snapshot (DigitalOcean → Volumes → Snapshots) and recreate.

## Restore from the off-site backup
On any Linux machine with restic (never paste the password anywhere but a terminal):
```
export RESTIC_REPOSITORY=s3:https://<account-id>.r2.cloudflarestorage.com/lacuna-backup
export AWS_ACCESS_KEY_ID=… AWS_SECRET_ACCESS_KEY=…   # an R2 token (dashboard → R2 → Manage API tokens)
export RESTIC_PASSWORD=…                             # BACKUP_PASSWORD from the password manager
restic snapshots --host lacuna
restic restore latest --host lacuna --target /restore      # gives /restore/data/{workspace,home}
```
Then copy `/restore/data` onto the new volume's `/data` (owner uid 10001) before starting the app.
