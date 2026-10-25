# Audio of episodes not opened for 14 days moves to Cloudflare R2 and comes back when opened; data disk 100 GB

- Date: 2026-10-25
- Status: CONFIRMED（Leon 2026-10-25「全部同意，都按着你的推荐」，第五批问题 1，甲）
- Supersedes / changes: changes `2026-10-19-cloud-deploy` (audio no longer only on our own server's disk)

20 beta shows for two months need about 140 GB; the 50 GB data disk can't hold it. Instead of a 250 GB disk now
and moving real users' data before paid launch, hot/cold tiering is built before the code freeze so it is tested
with everything else. `lacuna_app/cold.py` + `lacuna_app/r2.py` (SigV4, standard library only): once a day an
episode whose last use (opened, edited, exported: `used.json` / `state.json`) is 14+ days old, that is not in use
and whose declip cache is complete, has its source audio, recordings and export audio uploaded to the private
bucket `lacuna-audio` under content-addressed keys (`audio/<sha256>`), verified, and only then deleted from the
server; `<episode>/audio_store.json` lists what is where. Opening such an episode answers 423 with progress while
the audio comes back (about 10–30 s; the page shows 「正在取回音频」). Objects nothing refers to are deleted after 7
days. Staging reads the same bucket with a read-only token and never moves anything. The data disk grows
50 → 100 GB (online, `resize2fs` in bootstrap). Audio still never goes to the AI; it stays in our own storage
accounts (server disk + our private R2 bucket), encrypted at rest, and the nightly backup shrinks as audio leaves
the disk. No FLAC conversion. Going live needs a Provision recreate (Leon's typed 「重建服务器」) for the env vars.
