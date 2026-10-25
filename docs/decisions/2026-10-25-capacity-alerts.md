# Capacity alerts by the server's own mail, in the 8:00 digest and on the admin home page

- Date: 2026-10-25
- Status: CONFIRMED（Leon 2026-10-25「全部同意，都按着你的推荐」，第五批问题 6，甲）
- Supersedes / changes: replaces the single disk-above-70% alert of `2026-10-24-admin-site`

`lacuna_app/capacity.py`, collected in the admin's 5-minute round. Measures and thresholds (注意 / 该行动 / 紧急):
data disk 70 / 80 / 90 % or full within 21 / 10 / 3 days at the last 7 days' pace; import queue 7-day p90 wait
> 10 / 20 minutes, any wait > 45 minutes urgent; audio hours this month projected to month end at 60 / 80 / 100 %
of what the server can process (about 100 h per core, `LACUNA_CAPACITY_HOURS`); memory peak 75 / 85 %; accounts
40 / 45 / 50 of Cloudflare Access's free seats (only while Access is on). Each says what to do (grow the disk,
the next step of `docs/服务器容量与扩容预算_2026-10-20.md`, hold invites). Crossing a threshold mails the owner
at once (once a day per measure and level; a higher level mails again). No new token or cloud permission: a
server that is down entirely is caught by the hourly check from GitHub. AI spending keeps its own budget alert.
