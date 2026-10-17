"""Silence harmless disconnect noise in the server console.

When the browser aborts an audio stream (seek, pause, switching tracks), Windows' asyncio Proactor loop
logs a full `ConnectionResetError: [WinError 10054]` traceback through the `asyncio` logger. Nothing is
wrong: the client just hung up. This filter drops exactly those records and keeps every other asyncio
log, so real problems still show. We keep the default event loop (the Selector loop on Windows lacks
subprocess support, which ffmpeg/ASR need).
"""
from __future__ import annotations

import logging

_CLIENT_GONE = (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)


class ClientDisconnectFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        return not isinstance(exc, _CLIENT_GONE)


_FILTER = ClientDisconnectFilter()


def install() -> None:
    """Attach the filter to the asyncio logger (idempotent)."""
    logger = logging.getLogger("asyncio")
    if _FILTER not in logger.filters:
        logger.addFilter(_FILTER)
