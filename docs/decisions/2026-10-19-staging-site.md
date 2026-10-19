# Staging site: Leon checks new work before it ships

**Date:** 2026-10-19 · **Asked by:** Leon (05:57Z "等我验收通过之后，你直接自动部署到云"; 05:59Z "我要在 staging
上验收…staging 成功了，我就部署到 production。staging 不需要单收钱吧？")

## Decision
- **https://preview.lacunastudio.app** is staging. It is a second container (`lacuna-preview`) on the same
  server, behind the same tunnel and its own Cloudflare Access application with the same invite list, so the
  people who can reach the real site can reach staging, and nobody else can. You sign in the same way as on
  the real site, with the same account and the same two-step code.
- Its data is its own folder, `/data/preview` (mounted as `/data` in that container: it cannot see the real
  workspace). Each time a new version arrives on staging, the server first replaces that folder with a fresh
  copy of the real workspace, so Leon checks the change on his real episodes. Nothing done on staging reaches
  the real site. Staging has no Access token: an invite tried out there never changes who can reach the real
  site. Staging is left out of the nightly backup, because it is a copy.
- **Flow for every new request:** the thread opens its PR as usual and adds the **`staging`** label. When the
  PR's CI is green, the **Staging** workflow builds it, puts it on staging, and comments on the PR when it is
  live. Every later green push to that PR goes there again. The thread then asks Leon to check it on staging
  (thread label 「等你验收」). When Leon says it passes, the thread merges, and **Deploy** ships it to the real site
  as before. Staging shows one PR at a time: labelling a PR takes the label off the others, so threads take
  turns through the coordinator.
- Changes that can't be seen (docs, internal tooling) and urgent fixes may skip staging. While only Leon uses
  the real site, "ship without approval" still holds for those.
- **Cost: $0 extra.** Same droplet, same tunnel, Cloudflare Access Free (up to 50 people), one more DNS record
  on Leon's domain. The registry (basic, 5 GB) keeps one `preview` image beside `main` and the three newest
  builds. AI calls made while testing on staging cost the same as on the real site.
- Staging gives way to the real site: at most 2 CPUs and 3 GB of memory, and it is the first to stop if the
  server runs out of memory. A long import or export on staging can still make the real site a little slower.

## Where
`deploy/provision.py` (DNS, tunnel route, Access application, `preview.env`), `deploy/host/lacuna-update`
(`LACUNA_SEED_FROM`), `deploy/host/lacuna-update-preview.{service,timer}`, `.github/workflows/staging.yml`,
`deploy/ci.py wait-live <sha> preview`; the app shows 「预览站」 in the top bar (`LACUNA_STAGING=1`,
`web/src/features/staging/`). Rolled out with Provision `recreate` (a few minutes down, data volume kept).
