# Public version address for the deploy check (temporary)

Date: 2026-10-20. Decided by Leon (decision card + typed confirmation 04:56Z: 「现在可以开放…正式发布前撤回，要最安全的方式」).

## Context
The deploy check (`deploy/ci.py wait-live`, used by Deploy and Staging) created a short-lived Cloudflare Access
service token per run to read `/api/health` through Access. From 2026-10-20 02:39Z Cloudflare's service-token API
answered 504 for hours (create, list, delete), and the one token that was created got 401 for 30 min. Every deploy
check failed although both sites ran fine (the server updater pulls and rolls back on its own).

## Decision
- `GET /api/version` answers `{"version": …}` and nothing else, without an Access token (`lacuna_app/cloud.py`).
- A path-scoped Access application per site (`<domain>/api/version`, policy "LACUNA version (public)", bypass for
  everyone) lets it through Access; every other path keeps the full Access door (`deploy/provision.py version_door`).
- `wait-live` polls that address; no Cloudflare API call is needed to deploy. It still deletes the old check's
  leftover tokens when the API answers (best effort; the account caps service tokens).

## Withdraw before public launch
Leon wants the safest way before launch: remove the open path and use a long-lived service token stored as a
GitHub secret. Tracked in `docs/status/beta-launch-todo.md`.

Changed by: 2026-10-25-withdraw-public-version
