"""Where the server's time goes (Leon 2026-10-30: 删除这段 sometimes waits 10+ s and waveform tiles come late,
while the same request takes 0.05 s on a test machine). Kept in memory, never on disk, no names or ids:

* every slow API request (first byte later than ``SLOW_S``): its route with the ids masked, status, time to
  first byte, how long it waited for an episode's lock and who held the lock meanwhile, busy worker threads,
  the requests in flight by route, the load average;
* every long hold of an episode's lock (``TimedRLock``) and who held it;
* every stall of the event loop (``LAG_S``), with the requests in flight.

Read by ``GET /api/health/perf`` (routes/perf.py) and the workflow **Perf** (deploy/ci.py perf).
"""
from __future__ import annotations

import asyncio
import contextvars
import os
import re
import threading
import time
from collections import Counter, deque

SLOW_S = 0.5
HOLD_S = 0.5
LAG_S = 0.25
KEEP = 300

slow: deque = deque(maxlen=KEEP)
holds: deque = deque(maxlen=KEEP)
lags: deque = deque(maxlen=KEEP)
started = time.time()
_inflight: Counter = Counter()
_mu = threading.Lock()

# the request being served (route label + what it waited for), copied into worker threads with the context
REQ: contextvars.ContextVar[dict | None] = contextvars.ContextVar("lacuna_perf_req", default=None)

_MASKS = [
    (re.compile(r"^(/api/episodes/)[^/]+"), r"\1{ep}"),
    (re.compile(r"^(/api/spaces/)[^/]+"), r"\1{id}"),
    (re.compile(r"/audio/[^/]+\.wav$"), "/audio/{v}.wav"),
    (re.compile(r"/clips/[^/]+\.wav$"), "/clips/{c}.wav"),
]
_ID = re.compile(r"/(?=[^/]*\d)[^/]{6,}|/[^/]*[^\x00-\x7f][^/]*")


def route(method: str, path: str) -> str:
    """`GET /api/episodes/{ep}/manual/wave`: what was asked, without whose or which."""
    for rx, to in _MASKS:
        path = rx.sub(to, path)
    path = _ID.sub("/{x}", path)
    return f"{method} {path}"


def label() -> str:
    r = REQ.get()
    return r["route"] if r else f"job:{threading.current_thread().name.split('-')[0]}"


def _now() -> float:
    return round(time.time(), 1)


def _busy_threads() -> int | None:
    try:
        import anyio.to_thread
        return int(anyio.to_thread.current_default_thread_limiter().borrowed_tokens)
    except Exception:      # noqa: BLE001 - outside an event loop / another backend
        return None


def _load() -> float | None:
    try:
        return round(os.getloadavg()[0], 2)
    except OSError:
        return None


def _flight() -> dict:
    with _mu:
        return {k: v for k, v in _inflight.most_common(8)}


class TimedRLock:
    """`threading.RLock` that notes long waits (for the request waiting) and long holds (and by whom)."""

    def __init__(self):
        self._l = threading.RLock()
        self._depth = 0
        self.holder: str | None = None
        self._since = 0.0

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        if self._l.acquire(False):
            self._got()
            return True
        if not blocking:
            return False
        held_by, t = self.holder, time.perf_counter()
        ok = self._l.acquire(True, timeout)
        if ok:
            self._got()
            r = REQ.get()
            if r is not None:
                r["lock_wait"] += time.perf_counter() - t
                if held_by:
                    r["holders"].add(held_by)
        return ok

    def _got(self) -> None:
        if self._depth == 0:
            self.holder, self._since = label(), time.perf_counter()
        self._depth += 1

    def release(self) -> None:
        self._depth -= 1
        if self._depth == 0:
            held = time.perf_counter() - self._since
            if held >= HOLD_S:
                holds.append({"at": _now(), "by": self.holder, "s": round(held, 3)})
            self.holder = None
        self._l.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


class PerfMiddleware:
    """Times every /api/ request to its first byte and notes the slow ones (just inside the cloud gate)."""

    def __init__(self, app):
        self.app = app
        self._lag_task: asyncio.Task | None = None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            return await self.app(scope, receive, send)
        if self._lag_task is None:
            self._lag_task = asyncio.get_running_loop().create_task(_watch_lag())
        name = route(scope["method"], scope["path"])
        rec = {"route": name, "lock_wait": 0.0, "holders": set()}
        token = REQ.set(rec)
        t0 = time.perf_counter()
        busy, load = _busy_threads(), _load()
        seen: dict = {}
        with _mu:
            _inflight[name] += 1

        async def timed(msg):
            if msg["type"] == "http.response.start":
                seen["ttfb"] = time.perf_counter() - t0
                seen["status"] = msg["status"]
            await send(msg)

        try:
            await self.app(scope, receive, timed)
        finally:
            REQ.reset(token)
            with _mu:
                _inflight[name] -= 1
                if _inflight[name] <= 0:
                    del _inflight[name]
            ttfb = seen.get("ttfb", time.perf_counter() - t0)
            if ttfb >= SLOW_S:
                slow.append({"at": _now(), "route": name, "status": seen.get("status"), "ttfb": round(ttfb, 3),
                             "lock_wait": round(rec["lock_wait"], 3), "holders": sorted(rec["holders"]),
                             "threads_busy_at_start": busy, "load1": load, "in_flight": _flight()})


async def _watch_lag() -> None:
    loop = asyncio.get_running_loop()
    while True:
        t = loop.time()
        await asyncio.sleep(0.1)
        lag = loop.time() - t - 0.1
        if lag >= LAG_S:
            lags.append({"at": _now(), "s": round(lag, 3), "in_flight": _flight()})


def report() -> dict:
    return {"now": _now(), "up_s": round(time.time() - started), "load1": _load(), "threads_busy": _busy_threads(),
            "in_flight": _flight(), "slow": list(slow), "holds": list(holds), "lags": list(lags)}
