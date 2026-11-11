"""`GET /api/health/perf`: where the server's time goes (lacuna_app/perf.py). Masked routes and timings only."""
from __future__ import annotations

from .. import perf


def register(app, ctx) -> None:
    if ctx.option("space_child"):
        return

    @app.get("/api/health/perf")
    def perf_report():
        return perf.report()


def register_last(app, ctx) -> None:
    if ctx.option("space_child"):
        return
    from starlette.middleware import Middleware
    # just inside the cloud gate (and the admin site's host routing): times everything let in
    stack = app.user_middleware
    gate = next((i for i, m in enumerate(stack) if m.cls.__name__ == "CloudGate"), -1)
    stack.insert(gate + 1, Middleware(perf.PerfMiddleware))
