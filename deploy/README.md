# Cloud runbook (lacunastudio.app)

Decision: `docs/decisions/2026-10-19-cloud-deploy.md`. Status: `docs/status/cloud-deploy.md`.

## Pieces
| What | Where |
|---|---|
| App image | `Dockerfile`; smoke test `deploy/smoke_container.sh` (workflow **Cloud image**, on PRs) |
| Ship on green main | workflow **Deploy** → DO registry `:main` → server updater swaps it in, `deploy/ci.py wait-live` reads `/api/health` through Access with the service token in secrets `CF_DEPLOY_CLIENT_ID` / `CF_DEPLOY_CLIENT_SECRET` (without them: a token made for the run; decision `2026-10-25-withdraw-public-version`) |
| Create / change infra | workflow **Provision** (`plan` / `apply` / `recreate`) → `deploy/provision.py` |
| Server first boot | cloud-init built by `provision.py` from `deploy/host/*` (`lacuna-bootstrap`) |
| Server updater | `deploy/host/lacuna-update` (timer, every minute; waits for jobs; rolls back) |
| Staging | PR label `staging` → workflow **Staging** → registry `:preview` → `lacuna-update-preview` (fresh copy of the workspace in `/data/preview`, then the new version) → https://preview.lacunastudio.app |
| Backups | `deploy/host/lacuna-backup` (nightly restic → R2); workflow **Backup check** (daily: age, restore drill; Sundays: volume snapshot) |

GitHub secrets: `DIGITALOCEAN_TOKEN`, `CLOUDFLARE_API_TOKEN`, `ACCESS_EMAILS`, `BACKUP_PASSWORD`,
`ANTHROPIC_API_KEY`, `RESEND_API_KEY`, `CF_DEPLOY_CLIENT_ID`, `CF_DEPLOY_CLIENT_SECRET`. Workflow logs are public (public repo): scripts mask every secret
and print no emails or IPs.

## Common tasks
- **First setup**: Provision `plan`, then `apply`, then run **Deploy** by hand once (later merges deploy themselves).
- **Change a secret / a host script**: update it, then Provision `recreate` (a few minutes down; data volume kept).
- **Let someone in**: the app's invites add the email to the Access group; `ACCESS_EMAILS` only seeds it.
- **A deploy didn't go live**: the Deploy run says so after 30 min. Either a long import/export was running
  (it goes live when that finishes) or the new version failed its health check and the server went back
  to the previous one (`/var/lib/lacuna/deploy.json` + `failed-start.log` on the server). Fix forward with a PR.
- **Deploy-check token** (made once, rotated by running it again): Provision mode `deploy-token` with inputs
  `secrets_key` / `secrets_key_id` = the repository's Actions public key (`gh api
  repos/leon-qr-li/lacuna/actions/secrets/public-key`). The run prints the id and secret only sealed to that key;
  store them as `CF_DEPLOY_CLIENT_ID` / `CF_DEPLOY_CLIENT_SECRET` (`gh api -X PUT .../actions/secrets/<name>` with
  the sealed value and the key id).
- **Audio in cloud storage** (decision `2026-10-25-audio-cold-storage`): Provision `apply` makes the bucket
  `lacuna-audio` and its two tokens (server read-write, staging read-only) and grows the data volume; the app
  gets `LACUNA_AUDIO_*` only after a `recreate`.
- **Open the site door** (Cloudflare Access off, the app's own sign-in + Turnstile in front; decision
  `2026-10-21-app-sign-in`): only after Leon types 「关掉 Access」. Write `open` in `deploy/site-door.txt`
  (PR, merge), then Provision `recreate`. The Cloudflare token needs Account → Turnstile → Edit. Back:
  write `access`, merge, Provision `recreate`. A plain `apply` never changes the door.
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
