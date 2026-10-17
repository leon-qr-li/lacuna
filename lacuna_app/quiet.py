"""Silence harmless disconnect noise in the server console.

When the browser aborts an audio stream (seek, pause, switching tracks), Windows' asyncio Proactor loop
logs a full `ConnectionResetError: [WinError 10054]` traceback through the `asyncio` logger. Nothing is
wrong: the client just hung up. The same hang-up can also surface as asyncio's
"socket.send() raised exception." warnings (writes after the reset) or as uvicorn's
"Exception in ASGI application" with a disconnect exception. This filter drops exactly those records
and keeps every other log, so real problems still show. Two things are never hidden:
- a failed `accept()` (asyncio then closes the listening socket, so the App stops answering);
- any error whose exception is not a disconnect, even if a disconnect happened while handling it.
We keep the default event loop (the Selector loop on Windows lacks subprocess support, which
ffmpeg/ASR need).
"""
from __future__ import annotations

import logging

_CLIENT_GONE_NAMES = {"ClientDisconnect", "ClientDisconnected"}   # starlette.requests / uvicorn.protocols.utils
_CLIENT_GONE = (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)
_SEND_AFTER_RESET = "socket.send() raised exception."
_KEEP_PREFIXES = ("Accept failed",)
_LOGGERS = ("asyncio", "uvicorn.error")


def is_client_gone(exc: BaseException | None) -> bool:
    """True for a plain client hang-up, or an exception group made only of hang-ups."""
    if exc is None:
        return False
    if isinstance(exc, BaseExceptionGroup):
        return all(is_client_gone(e) for e in exc.exceptions)
    return isinstance(exc, _CLIENT_GONE) or type(exc).__name__ in _CLIENT_GONE_NAMES


class ClientDisconnectFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg == _SEND_AFTER_RESET:
            return False
        exc = record.exc_info[1] if record.exc_info else None
        if not is_client_gone(exc):
            return True
        return str(record.msg).startswith(_KEEP_PREFIXES)


_FILTER = ClientDisconnectFilter()


def install() -> None:
    """Attach the filter to the asyncio and uvicorn error loggers (idempotent)."""
    for name in _LOGGERS:
        logger = logging.getLogger(name)
        if _FILTER not in logger.filters:
            logger.addFilter(_FILTER)
