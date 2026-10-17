"""Workspace path safety (`store.inside`)."""
from pathlib import Path

import pytest

from lacuna_app import store
from lacuna_app.store import PathError, inside


def test_inside_joins_and_refuses_escapes(tmp_path):
    assert inside(tmp_path, "exports", "EP_TEST_合成", "publish", "notes.md") == \
        tmp_path.resolve() / "exports" / "EP_TEST_合成" / "publish" / "notes.md"
    with pytest.raises(PathError):
        inside(tmp_path, "..", "elsewhere")


def test_inside_ignores_the_windows_verbatim_prefix(tmp_path, monkeypatch):
    # Windows: resolving a not-yet-existing path while another thread creates part of it can return
    # "\\?\C:\..." (seen on CI as "path escapes" during a background publish-pack write)
    real = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: Path("\\\\?\\" + str(real(self))))
    p = inside(tmp_path, "exports", "EP", "publish", "notes.md")
    assert p == real(tmp_path) / "exports" / "EP" / "publish" / "notes.md"
    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: Path("\\\\?\\UNC\\" + str(real(self))))
    assert str(store._resolve(tmp_path)).startswith("\\\\?\\UNC\\")     # UNC form left alone
