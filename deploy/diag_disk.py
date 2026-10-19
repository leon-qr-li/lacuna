"""One-off: disk / memory / cpu of the server from DigitalOcean monitoring (no IPs or names printed)."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci import do
from provision import TAG

d = do()
drops = d.http("GET", f"/v2/droplets?tag_name={TAG}").get("droplets", [])
print("droplets:", len(drops))
end = int(time.time()); start = end - 6 * 3600
for dr in drops:
    hid = dr["id"]
    print("status", dr.get("status"), "disk GB", dr.get("disk"), "mem MB", dr.get("memory"))
    for metric in ("filesystem_free", "filesystem_size", "memory_available", "memory_total", "load_5"):
        try:
            out = d.http("GET", f"/v2/monitoring/metrics/droplet/{metric}?host_id={hid}&start={start}&end={end}")
        except Exception as e:
            print(metric, "error", type(e).__name__, str(e)[:200]); continue
        for r in out.get("data", {}).get("result", []):
            m = r.get("metric", {})
            vals = r.get("values", [])
            pts = vals[::max(1, len(vals)//12)] + vals[-1:]
            fmt = lambda v: f"{float(v)/1e9:.2f}G" if "filesystem" in metric or "memory" in metric else f"{float(v):.2f}"
            print(metric, m.get("mountpoint", ""), m.get("device", ""),
                  " ".join(f"{time.strftime('%H:%M', time.gmtime(t))}={fmt(v)}" for t, v in pts))
