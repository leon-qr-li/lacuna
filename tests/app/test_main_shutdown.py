"""Shutdown must not hang on a connection the browser keeps open (a paused <audio> holding its WAV
stream)."""
from __future__ import annotations

import socket
import threading
import time

from starlette.applications import Starlette
from starlette.responses import StreamingResponse
from starlette.routing import Route

from lacuna_app import __main__ as main_mod


def _endless(request):
    async def gen():
        while True:
            yield b"\0" * 65536
    return StreamingResponse(gen(), media_type="audio/wav")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_server_stops_despite_an_open_stream():
    port = _free_port()
    server = main_mod.make_server(Starlette(routes=[Route("/stream", _endless)]), port)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    end = time.monotonic() + 10
    while not server.started and time.monotonic() < end:
        time.sleep(0.05)
    assert server.started

    client = socket.create_connection(("127.0.0.1", port))
    client.sendall(b"GET /stream HTTP/1.1\r\nHost: x\r\n\r\n")
    assert client.recv(1024)            # streaming started; the client now stops reading
    time.sleep(0.5)                     # let the socket buffers fill so the server blocks on send

    t0 = time.monotonic()
    server.should_exit = True
    t.join(main_mod.GRACEFUL_SHUTDOWN + 7)
    client.close()
    assert not t.is_alive(), "server did not stop while a stream was open"
    assert time.monotonic() - t0 < main_mod.GRACEFUL_SHUTDOWN + 7

