"""Per-feature setup of the E2E servers (tests/app/serve_e2e.py), one module per feature.

Each module defines `configure(mode, ws, svc)`, called for every server mode ("default", "ai",
"import"); it puts the feature's fakes into `svc`, the keyword arguments for `create_app`.
Modules run in (ORDER, name) order (default ORDER 50), so one can use what an earlier one set.
A new feature adds a module here instead of editing serve_e2e.py.
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path


def configure_all(mode: str, ws: Path, svc: dict) -> dict:
    mods = [importlib.import_module(f"{__name__}.{m.name}") for m in pkgutil.iter_modules(__path__)
            if not m.name.startswith("_")]
    for mod in sorted(mods, key=lambda m: (getattr(m, "ORDER", 50), m.__name__)):
        mod.configure(mode, ws, svc)
    return svc
