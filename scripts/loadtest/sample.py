"""Sample a process's CPU and memory every few seconds while a load test runs (Linux /proc).

    python scripts/loadtest/sample.py <pid> <out.csv> [--every 2]

Columns: unix time, CPU % of one core (400 = four cores busy), resident memory MB, threads, open files.
Stops when the process ends or on Ctrl+C.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

TICK = os.sysconf("SC_CLK_TCK")


def cpu_s(pid: int) -> float:
    f = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return (int(f[11]) + int(f[12])) / TICK          # utime + stime


def status(pid: int) -> dict:
    out = {}
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        k, _, v = line.partition(":")
        out[k] = v.strip()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pid", type=int)
    ap.add_argument("out")
    ap.add_argument("--every", type=float, default=2.0)
    a = ap.parse_args()
    with open(a.out, "w") as f:
        f.write("t,cpu_pct,rss_mb,threads,fds\n")
        last_t, last_c = time.time(), cpu_s(a.pid)
        while True:
            time.sleep(a.every)
            try:
                c, st = cpu_s(a.pid), status(a.pid)
                fds = len(os.listdir(f"/proc/{a.pid}/fd"))
            except (FileNotFoundError, ProcessLookupError):
                break
            now = time.time()
            pct = 100 * (c - last_c) / (now - last_t)
            last_t, last_c = now, c
            rss = int(st["VmRSS"].split()[0]) / 1024
            f.write(f"{now:.1f},{pct:.0f},{rss:.0f},{st['Threads']},{fds}\n")
            f.flush()


if __name__ == "__main__":
    main()
