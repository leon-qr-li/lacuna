"""Shutdown must not hang on a connection the browser keeps open (a paused <audio> holding its WAV
stream)."""
from __future__ import annotations

import socket
import threading
import time

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, StreamingResponse
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



def test_idle_connections_outlive_the_proxys():
    """cloudflared keeps idle connections to us 90 s; ours must stay open longer, or a request the proxy sends
    just as we close one (the page's 5-second presence beat) gets a reset and the visitor a 502 (batch 10)."""
    server = main_mod.make_server(Starlette(), _free_port())
    assert server.config.timeout_keep_alive == main_mod.KEEP_ALIVE > 90
    assert server.config.timeout_graceful_shutdown == main_mod.GRACEFUL_SHUTDOWN


def test_a_post_after_a_five_second_pause_reuses_the_connection():
    port = _free_port()
    server = main_mod.make_server(Starlette(routes=[Route("/p", lambda r: PlainTextResponse("ok"), methods=["POST"])]),
                                  port)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    end = time.monotonic() + 10
    while not server.started and time.monotonic() < end:
        time.sleep(0.05)
    c = socket.create_connection(("127.0.0.1", port))
    c.settimeout(5)

    def ask() -> bytes:
        c.sendall(b"POST /p HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n")
        got = b""
        while not got.endswith(b"ok"):
            part = c.recv(1024)
            if not part:
                return got              # the server closed the connection
            got += part
        return got

    try:
        assert ask().startswith(b"HTTP/1.1 200")
        time.sleep(5.5)                 # longer than uvicorn's default 5 s keep-alive
        assert ask().startswith(b"HTTP/1.1 200")
    finally:
        c.close()
        server.should_exit = True
        t.join(10)
