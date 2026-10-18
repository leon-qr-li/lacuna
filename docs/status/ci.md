# CI speed (2026-10-18)

Decision: `docs/decisions/2026-10-18-ci-speedup.md`. Workflow: `.github/workflows/ci.yml`.

Jobs per OS (windows / macos / ubuntu): `pytest <os>` (only when Python changed, `-n auto`),
`e2e <os> 1/2` and `e2e <os> 2/2` (Python or web changed), `install <os>` (installer / pyproject changed).
"CI ok" is the merge gate.

| | before (full run) | after |
|---|---|---|
| wall time | 5–7.5 min (Windows) | _pending first runs_ |

Open: if a shard becomes much slower than the other as specs are added, rebalance (Playwright shards by file).
