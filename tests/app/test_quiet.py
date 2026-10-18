"""Browser-abort disconnects (WinError 10054) don't spam the console; other errors still log."""
import asyncio
import logging
import socket
import struct
import threading
import time

import pytest

from lacuna_app import quiet


class _Grab(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def records():
    quiet.install()
    quiet.install()   # idempotent
    h = _Grab()
    for name in quiet._LOGGERS:
        logging.getLogger(name).addHandler(h)
    yield h.records
    for name in quiet._LOGGERS:
        logging.getLogger(name).removeHandler(h)


def _report(exc: BaseException, message: str = "Exception in callback _call_connection_lost()") -> None:
    loop = asyncio.new_event_loop()
    try:
        loop.call_exception_handler({"message": message, "exception": exc})
    finally:
        loop.close()


class ClientDisconnect(Exception):      # same name as starlette.requests.ClientDisconnect
    pass


class ClientDisconnected(OSError):      # same name as uvicorn.protocols.utils.ClientDisconnected
    pass


GONE = [
    ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host"),
    ConnectionAbortedError(10053, "aborted"),
    BrokenPipeError(32, "Broken pipe"),
]


@pytest.mark.parametrize("exc", GONE)
def test_client_disconnect_is_silenced(records, exc):
    _report(exc)
    assert records == []


def test_other_errors_still_logged(records):
    _report(RuntimeError("real bug"))
    assert len(records) == 1
    assert "real bug" in str(records[0].exc_info[1])


def test_failed_accept_still_logged(records):
    """asyncio closes the listening socket after this one: hiding it would hide a dead App."""
    _report(ConnectionResetError(10054, "reset"), message="Accept failed on a socket")
    assert len(records) == 1


def test_send_after_reset_warning_is_silenced(records):
    logging.getLogger("asyncio").warning("socket.send() raised exception.")
    logging.getLogger("asyncio").warning("something else")
    assert [r.getMessage() for r in records] == ["something else"]


@pytest.mark.parametrize("exc", [ClientDisconnect(), ClientDisconnected(), *GONE,
                                 ExceptionGroup("tg", [ClientDisconnect(), ConnectionResetError()])])
def test_asgi_disconnect_is_silenced(records, exc):
    logging.getLogger("uvicorn.error").error("Exception in ASGI application\n", exc_info=exc)
    assert records == []


@pytest.mark.parametrize("exc", [ValueError("real bug"),
                                 ExceptionGroup("tg", [ClientDisconnect(), ValueError("real bug")])])
def test_asgi_real_error_still_logged(records, exc):
    logging.getLogger("uvicorn.error").error("Exception in ASGI application\n", exc_info=exc)
    assert len(records) == 1


def test_real_error_raised_while_handling_disconnect_still_logged(records):
    try:
        try:
            raise ConnectionResetError(10054, "reset")
        except ConnectionResetError:
            raise KeyError("real bug")
    except KeyError as e:
        exc = e
    logging.getLogger("uvicorn.error").error("Exception in ASGI application\n", exc_info=exc)
    assert len(records) == 1


def test_filter_installed_once():
    quiet.install()
    quiet.install()
    for name in quiet._LOGGERS:
        assert logging.getLogger(name).filters.count(quiet._FILTER) == 1


def test_main_installs_filter(monkeypatch, tmp_path):
    import lacuna_app.__main__ as m
    import uvicorn
    for name in quiet._LOGGERS:
        logging.getLogger(name).removeFilter(quiet._FILTER)
    monkeypatch.setattr(uvicorn.Server, "run", lambda self: None)
    m.main(["--workspace", str(tmp_path), "--no-browser", "--editor", "mock"])
    for name in quiet._LOGGERS:
        assert quiet._FILTER in logging.getLogger(name).filters


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_real_browser_abort_mid_stream_is_quiet(records):
    """A real uvicorn server (Proactor loop on Windows, as on Leon's PC) streams audio-sized data;
    the client hangs up with a TCP reset several times, like seeking in the player."""
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import StreamingResponse

    app = FastAPI()

    @app.get("/audio")
    def audio():
        def chunks():
            for _ in range(2000):
                yield b"\0" * 65536
        return StreamingResponse(chunks(), media_type="audio/wav")

    @app.get("/boom")
    def boom():
        raise RuntimeError("real bug")

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    # uvicorn's logging setup replaces its loggers' handlers but must keep our filter
    assert quiet._FILTER in logging.getLogger("uvicorn.error").filters
    grab = _Grab()
    grab.records = records
    logging.getLogger("uvicorn.error").addHandler(grab)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        for _ in range(5):
            c = socket.create_connection(("127.0.0.1", port))
            c.sendall(b"GET /audio HTTP/1.1\r\nHost: x\r\n\r\n")
            c.recv(65536)
            c.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))   # RST, not FIN
            c.close()
        time.sleep(1.0)
        noise = [r for r in records if r.levelno >= logging.WARNING]
        assert noise == [], [r.getMessage() for r in noise]

        c = socket.create_connection(("127.0.0.1", port))   # a real error still reaches the console
        c.sendall(b"GET /boom HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        assert b"500" in c.recv(4096).split(b"\r\n")[0]
        c.close()
        time.sleep(0.3)
        assert any("real bug" in str(r.exc_info[1]) for r in records if r.exc_info)
    finally:
        server.should_exit = True
        t.join(10)
        logging.getLogger("uvicorn.error").removeHandler(grab)
