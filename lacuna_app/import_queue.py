"""Imports wait their turn, across every show on the server (batch 5, decision 2026-10-24-upload-and-queue).

An import's speech recognition fills every core and holds each track decoded in memory (1.5-2.5 GB), so
two or three at once on the 8 GB server could take the whole site down. Every workspace's Importer passes
through one gate: at most ``LACUNA_IMPORT_SLOTS`` imports (default 1) recognise at a time, the rest wait in
order of arrival. An import leaves the gate before its AI first cut (that step only waits on the network),
so the next one's recognition starts meanwhile.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Callable


class Abandoned(Exception):
    """The import was cancelled while it waited."""


class Gate:
    def __init__(self, slots: int = 1):
        self.slots = max(1, slots)
        self._cv = threading.Condition()
        self._waiting: list[str] = []
        self._holding: set[str] = set()
        self._since: dict[str, float] = {}
        self.waits: deque[tuple[float, float]] = deque(maxlen=1000)   # (when it started, seconds it waited)

    def enter(self, key: str, cancelled: Callable[[], bool] = lambda: False, tick: float = 0.25) -> None:
        """Wait until `key` may run; raises Abandoned if `cancelled()` turns true first."""
        with self._cv:
            self._waiting.append(key)
            self._since[key] = time.time()
            try:
                while len(self._holding) + self._waiting.index(key) >= self.slots:
                    if cancelled():
                        raise Abandoned()
                    self._cv.wait(tick)
                if cancelled():
                    raise Abandoned()
                self._holding.add(key)
                now = time.time()
                self.waits.append((now, now - self._since[key]))
            finally:
                self._waiting.remove(key)
                self._since.pop(key, None)
                self._cv.notify_all()

    def leave(self, key: str) -> None:
        """Done with the heavy part (calling it twice is harmless)."""
        with self._cv:
            self._holding.discard(key)
            self._cv.notify_all()

    def ahead(self, key: str) -> int | None:
        """How many imports run or wait before `key`; None if it isn't waiting."""
        with self._cv:
            if key not in self._waiting:
                return None
            return len(self._holding) + self._waiting.index(key)

    def load(self) -> dict:
        """Now: running, waiting, and how long the longest-waiting import has waited (seconds)."""
        with self._cv:
            now = time.time()
            return {"running": len(self._holding), "waiting": len(self._waiting), "slots": self.slots,
                    "longest": round(max((now - t for t in self._since.values()), default=0.0), 1)}


GATE = Gate(int(os.environ.get("LACUNA_IMPORT_SLOTS", "1") or 1))
