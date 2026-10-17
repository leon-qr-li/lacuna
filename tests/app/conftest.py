import pytest


@pytest.fixture(autouse=True)
def no_registry_key(monkeypatch):
    """Tests decide the API key through the environment only: on Leon's PC the real key also
    sits in the Windows registry, which find_api_key would otherwise pick up."""
    from lacuna_app import editor
    monkeypatch.setattr(editor, "_windows_registry_key", lambda: None)
