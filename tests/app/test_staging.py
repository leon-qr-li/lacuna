"""The staging site flag (decision staging-site): only a cloud server started with LACUNA_STAGING=1."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from lacuna_app import cloud, create_app
from lacuna_app.editor import MockEditorAdapter


def test_staging_needs_cloud_mode(monkeypatch):
    monkeypatch.setenv("LACUNA_STAGING", "1")
    monkeypatch.delenv("LACUNA_CLOUD", raising=False)
    assert cloud.staging() is False
    monkeypatch.setenv("LACUNA_CLOUD", "1")
    assert cloud.staging() is True
    monkeypatch.delenv("LACUNA_STAGING")
    assert cloud.staging() is False


def test_app_info_says_whether_this_is_staging(tmp_path, monkeypatch):
    monkeypatch.delenv("LACUNA_CLOUD", raising=False)
    monkeypatch.setenv("LACUNA_STAGING", "1")      # ignored on the desktop
    c = TestClient(create_app(tmp_path / "ws", MockEditorAdapter(), web_dist=Path("/nonexistent")))
    assert c.get("/api/app").json()["staging"] is False
    assert c.get("/api/staging").json() == {"staging": False}
