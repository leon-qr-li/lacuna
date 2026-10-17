"""Browser-abort disconnects (WinError 10054) don't spam the console; other asyncio errors still log."""
import asyncio
import logging

import pytest

from lacuna_app import quiet


@pytest.fixture
def asyncio_records():
    quiet.install()
    quiet.install()   # idempotent
    records: list[logging.LogRecord] = []

    class Grab(logging.Handler):
        def emit(self, record):
            records.append(record)

    h = Grab()
    logger = logging.getLogger("asyncio")
    logger.addHandler(h)
    yield records
    logger.removeHandler(h)


def _report(exc: BaseException) -> None:
    loop = asyncio.new_event_loop()
    try:
        loop.call_exception_handler({"message": "Exception in callback _call_connection_lost()", "exception": exc})
    finally:
        loop.close()


@pytest.mark.parametrize("exc", [
    ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host"),
    ConnectionAbortedError(10053, "aborted"),
    BrokenPipeError(32, "Broken pipe"),
])
def test_client_disconnect_is_silenced(asyncio_records, exc):
    _report(exc)
    assert asyncio_records == []


def test_other_errors_still_logged(asyncio_records):
    _report(RuntimeError("real bug"))
    assert len(asyncio_records) == 1
    assert "real bug" in str(asyncio_records[0].exc_info[1])


def test_filter_installed_once():
    quiet.install()
    quiet.install()
    assert logging.getLogger("asyncio").filters.count(quiet._FILTER) == 1


def test_main_installs_filter(monkeypatch, tmp_path):
    import lacuna_app.__main__ as m
    import uvicorn
    logging.getLogger("asyncio").removeFilter(quiet._FILTER)
    monkeypatch.setattr(uvicorn.Server, "run", lambda self: None)
    m.main(["--workspace", str(tmp_path), "--no-browser", "--editor", "mock"])
    assert quiet._FILTER in logging.getLogger("asyncio").filters
