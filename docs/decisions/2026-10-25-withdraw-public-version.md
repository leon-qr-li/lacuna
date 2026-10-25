# The public /api/version is withdrawn; the deploy check reads /api/health with a long-lived Access service token

- Date: 2026-10-25
- Status: CONFIRMED（Leon 2026-10-25 打字「全部同意，都按着你的推荐」，第五批问题 7，安全改动）
- Supersedes / changes: changes `2026-10-20-public-version-check`

Nothing on lacunastudio.app or staging is reachable without signing in any more, not even the version.
`lacuna_app/cloud.py` drops the open path; `deploy/provision.py` mode `close-version-door` deletes the two
「version」 Access apps and their bypass policy (Provision apply runs it). The deploy check (`deploy/ci.py
wait_live`) sends `CF-Access-Client-Id` / `-Secret` from GitHub secrets `CF_DEPLOY_CLIENT_ID` /
`CF_DEPLOY_CLIENT_SECRET`, a service token `lacuna-deploy` made by Provision mode `deploy-token` (printed only
sealed to the repository's Actions public key, then stored as secrets). Until those secrets exist it falls back
to a token made for the one run and deleted after (the token sweep). If Cloudflare's token API fails, the deploy
check waits; the site itself is unaffected.
