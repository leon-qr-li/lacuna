# LACUNA runs in the cloud: DigitalOcean + Cloudflare Tunnel/Access, deployed on every green main

- Date: 2026-10-19
- Status: CONFIRMED（Leon 2026-10-19 00:06Z / 01:24Z: DigitalOcean, audio in the cloud, invite-only, deploy pipeline; domain lacunastudio.app bought 02:32Z）
- Supersedes / changes: CLAUDE.md "Audio and user media never leave the machine" → "never go to the AI"; D51 (desktop self-update) stays for the desktop app until the cloud replaces it

Analysis and prices: `/mnt/project-files/lacuna/docs/云端部署分析_2026-10-19.md` (project files).

**Shape**
- One DigitalOcean droplet, SFO3, 4 vCPU / 8 GB, Ubuntu 24.04. No inbound ports at all (DO cloud firewall
  with no inbound rules + ufw deny). The droplet dials out to Cloudflare (`cloudflared`, remotely managed
  tunnel); the server's IP is never published.
- Two doors: Cloudflare Access (invite email list, email one-time code) in front of `lacunastudio.app`,
  then the app's own sign-in (+ mandatory 2FA, thread 「账号与权限」). The app also verifies the Access
  token on every request (`lacuna_app/cloud.py`), so a request that bypassed Access is refused (fail closed).
- Data: the whole workspace on one DO block-storage volume (`/data`; encrypted at rest by DO), so the
  droplet itself is disposable and is rebuilt from code. Audio is stored there, never sent to the AI.
- Backups: nightly encrypted restic snapshot of `/data` to Cloudflare R2 (another company, survives losing
  the DO account); 30 daily + 12 monthly kept; restic password only in GitHub secrets + Leon's password manager.
- Deploy: CI green on main → image built and pushed to DO Container Registry → the droplet's updater pulls
  it within a minute, waits while an import / export / publish job runs, swaps the container, health-checks,
  and rolls back to the previous image if the new one doesn't come up.
- Secrets live only in GitHub Actions secrets and on the droplet (root-only env file); never in the repo
  (the repo is public), never in logs, never in the browser. API keys can't be changed from the web UI in cloud mode.

**Why this and not …**: see the analysis (AWS / Fly / Hetzner / Render compared). DOCR instead of GHCR
because the image must stay pullable if the repo goes private; pull-based updater instead of SSH push so
the droplet needs no inbound port and no long-lived deploy key.

Changed by: 2026-10-25-audio-cold-storage
