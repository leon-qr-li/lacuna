# Editor over a bad connection + 位置记忆 (2026-10-30)

State: built, PR open (branch `claude/project-thread-ohj12z`). Decision `2026-10-30-http3-off`.

Leon's seven reports of 2026-10-30, and where each went:
1. 新建节目 first 确认 "Failed to fetch": `web/src/api.ts` sends a request with no answer once more.
2./4./5. 删除这段 / 只静音 hung, buttons grey until refresh, refresh 20-60 s: dropped HTTP/3 connection (server
   is fast: cut 34 ms on a 51-min episode). Manual cut, waveform tiles and transcript stretches time out after 20 s
   (`WAIT_MS`, `features/manual/api.ts`); a failed edit action reloads the episode (`App.tsx` run); Cloudflare
   HTTP/3 off via Provision `http3-off` (`deploy/provision.py`).
3. Waveform empty past a point: `features/manual/chunks.ts` asks again for chunks that failed (4 tries); after a
   cut the old tiles show until the new ones arrive (`keepOld`), so the lanes do not blink empty.
6./7. 整集试听: from 审阅 always starts at 0; refresh / leave+return / other tabs return to the last place (审阅 still jumps to its edit), per episode in localStorage `lacuna.pos.<id>`
   (`features/positions/usePositions.ts`); restored on refresh and on coming back to the episode.

Tests: `web/e2e/network_retry.spec.ts`, `web/e2e/editor_network.spec.ts`, `tests/test_provision.py`.
Next: after merge run Provision `http3-off` (needs the Cloudflare token to have Zone Settings edit; if refused,
Leon turns it off in the dashboard: Speed → Optimization → Protocol Optimization → HTTP/3).

## Round 2 (Leon 2026-10-30 20:38Z): still waits 10+ s sometimes after HTTP/3 was turned off
- Leon turned HTTP/3 off himself. The page now recovers by itself and refreshes are fast, but 删除这段 still
  sometimes waits 10+ s, and waveform tiles come late while playing.
- Same request on a 51-min test episode: 0.05 s, also with a full audio stream and tile requests running alongside
  (scratch load test). So something on the real server holds it up. Measuring it there: `lacuna_app/perf.py`
  (slow requests with masked routes, waits for an episode's lock and who held it, busy worker threads, event-loop
  stalls; in memory only), `GET /api/health/perf`, workflow **Perf** (`deploy/ci.py perf`) prints it.
- Waveform: the next page of tiles is fetched ahead, so playback turning the page finds them there.
- Next: Leon reproduces a few times, run **Perf**, fix the cause it shows.
