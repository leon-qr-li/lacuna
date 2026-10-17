import pytest


@pytest.fixture(autouse=True)
def no_registry_key(monkeypatch):
    """Tests decide the API key through the environment only: on Leon's PC the real key also
    sits in the Windows registry (on a Mac in the Keychain, elsewhere in a file), which
    find_api_key would otherwise pick up."""
    from lacuna_app import editor
    monkeypatch.setattr(editor, "_windows_registry_key", lambda: None)
    monkeypatch.setattr(editor, "_macos_keychain_key", lambda: None)
    monkeypatch.setattr(editor, "_file_key", lambda: None)
