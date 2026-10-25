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


@pytest.fixture(autouse=True)
def fresh_import_queue(monkeypatch):
    """Each test gets its own import queue: an import thread a test leaves behind never makes the next
    test's imports wait (lacuna_app/import_queue.py)."""
    from lacuna_app import import_queue
    monkeypatch.setattr(import_queue, "GATE", import_queue.Gate(1))


@pytest.fixture(autouse=True)
def no_uploads_under_way(monkeypatch):
    """Uploads a test left unfinished don't count as under way in the next one (upload_parts.active)."""
    from lacuna_app import upload_parts
    monkeypatch.setattr(upload_parts, "_live", {})
