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


def test_windows_sharing_violation_is_retried(tmp_path, monkeypatch):
    """Windows: reading a JSON file while another thread replaces it briefly raises PermissionError."""
    from lacuna_app import store

    monkeypatch.setattr(store.sys, "platform", "win32")
    monkeypatch.setattr(store.time, "sleep", lambda s: None)
    f = tmp_path / "poster.json"
    store.atomic_write_json(f, {"v": 1})
    real = Path.read_text
    fails = {"n": 2}

    def flaky(self, *a, **k):
        if self == f and fails["n"]:
            fails["n"] -= 1
            raise PermissionError(13, "Permission denied")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", flaky)
    assert store.read_json(f) == {"v": 1}
    assert fails["n"] == 0

    real_replace = store.os.replace
    busy = {"n": 2}

    def flaky_replace(src, dst):
        if Path(dst) == f and busy["n"]:
            busy["n"] -= 1
            raise PermissionError(13, "Permission denied")
        return real_replace(src, dst)

    monkeypatch.setattr(store.os, "replace", flaky_replace)
    store.atomic_write_json(f, {"v": 2})
    assert busy["n"] == 0 and store.read_json(f) == {"v": 2}


def test_permission_error_is_not_retried_elsewhere(tmp_path, monkeypatch):
    from lacuna_app import store

    monkeypatch.setattr(store.sys, "platform", "linux")
    calls = []

    def denied():
        calls.append(1)
        raise PermissionError(13, "Permission denied")

    with pytest.raises(PermissionError):
        store._retry_windows(denied)
    assert calls == [1]
