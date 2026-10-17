"""Route modules are discovered (lacuna_app/routes/), packaged, and take injected services."""
import importlib
import tomllib
from pathlib import Path

from lacuna_app import routes
from lacuna_app.publish import Publisher
from lacuna_app.server import create_app
from lacuna_app.store import Workspace

ROOT = Path(__file__).resolve().parents[2]


def test_every_route_module_registers():
    names = routes.modules()
    assert {"episodes", "export", "imports", "library", "music", "publish", "poster", "learning"} <= set(names)
    for n in names:
        assert callable(importlib.import_module(f"lacuna_app.routes.{n}").register), n


def test_every_package_is_installed():
    """setuptools lists packages explicitly: a new subpackage missing here works from a checkout
    but is absent from an installed copy."""
    listed = set(tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["tool"]["setuptools"]["packages"])
    for top in ("lacuna_core", "lacuna_app"):
        for init in (ROOT / top).rglob("__init__.py"):
            pkg = ".".join(init.parent.relative_to(ROOT).parts)
            assert pkg in listed, f"add {pkg!r} to [tool.setuptools] packages in pyproject.toml"


def test_injected_service_is_used_and_shared(tmp_path):
    pub = Publisher(Workspace(tmp_path).ensure())
    app = create_app(tmp_path, publisher=pub)
    assert app.state.publisher is pub
    assert app.state.posters.publisher is pub       # the cover module builds on the same publisher
    assert app.state.ctx.provide("publisher") is pub
