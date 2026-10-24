"""One module per feature, each exposing `register(app, ctx)` (ctx = `server.AppContext`).

Every module in this package is registered automatically, in name order, so adding a feature
means adding a file here, not editing a shared list. Modules whose name starts with `_` are
helpers and are skipped. A module may also have `register_last(app, ctx)`, run after every module's
`register`: middleware added there sits outside all the others (the admin site's host routing).
"""
from __future__ import annotations

import importlib
import pkgutil


def modules() -> list[str]:
    return sorted(m.name for m in pkgutil.iter_modules(__path__) if not m.name.startswith("_"))


def register_all(app, ctx) -> None:
    mods = [importlib.import_module(f"{__name__}.{name}") for name in modules()]
    for m in mods:
        m.register(app, ctx)
    for m in mods:
        if hasattr(m, "register_last"):
            m.register_last(app, ctx)
