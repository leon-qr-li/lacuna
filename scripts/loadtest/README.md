# Load test (batch 10)

A local copy of the site in cloud mode, many signed-in people working at once, measured with k6. Nothing
leaves the machine: no AI call (mock editor, no key), no ASR, no mail, no cloud storage.

```bash
python scripts/loadtest/make_site.py /tmp/lt --users 150 --minutes 60     # ~3 min; 151 people, one 60-min episode each
env -u ANTHROPIC_API_KEY LACUNA_CLOUD=1 LACUNA_ACCESS=off \
  python -m lacuna_app --workspace /tmp/lt/ws --port 8790 --no-browser --editor mock &
python scripts/loadtest/sample.py $! /tmp/lt/sample.csv &                  # server CPU / memory every 2 s
k6 run -e SITE=/tmp/lt/site.json -e BASE=http://127.0.0.1:8790 -e PLAN=ramp scripts/loadtest/lacuna.js
```

`lacuna.js` knobs (`-e NAME=value`): `PLAN` ramp | spike | soak; `STEPS` online people per step (ramp,
30 s up + `HOLD` each); `REVIEW_S` / `AB_S` average seconds between review decisions / A/B listens;
`IDLE=1` page open only (presence beat); `SESSION_S` length of one editing session; `IMPORTERS` VUs
watching the import list. Add `--out csv=reqs.csv.gz` for per-request timings.

What it does not cover: Cloudflare (Access, tunnel), the network between people and the server, real
imports / exports / AI (CPU-heavy jobs, measured in `docs/status/perf.md`), uploads. Results and the
capacity read-out: `docs/status/batch-10.md`.
