"""Localized preview: render only [t - ctx, t + ctx] (5 s either side by default) of a timeline, with a segment cache.

The window is rendered as fixed blocks on an absolute grid. Each block is cached under
`Renderer.range_key` (a hash of exactly the content that affects that block), so:
* an edit far away leaves the key - and the cached audio - untouched;
* an upstream cut that shifts material into a block changes its key (no stale audio);
* undo returns to keys that are still cached.
"""
from __future__ import annotations

import threading
import time
import weakref
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np

from .edl import Timeline
from .render import Renderer


class SharedBudget:
    """One byte budget over several `SegmentCache`s: when their total goes over it, the least recently used
    block of any of them goes first. The server keeps one per process, so the preview caches of every
    open episode in every show together stay under it (each cache alone also keeps its own limit)."""

    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        self.bytes = 0
        self.lock = threading.RLock()       # RLock: a cache let go mid-operation clears itself (__del__)
        # (id of the cache, block key) -> the cache, weakly: an episode let go frees its blocks at once
        self._order: OrderedDict[tuple[int, str], weakref.ref] = OrderedDict()


class SegmentCache:
    """In-memory LRU with a byte budget (and optionally a `SharedBudget` it counts against too)."""

    def __init__(self, max_bytes: int = 256 << 20, shared: SharedBudget | None = None):
        self.max_bytes = max_bytes
        self.shared = shared
        self._lock = shared.lock if shared is not None else threading.Lock()
        self._d: OrderedDict[str, np.ndarray] = OrderedDict()
        self.bytes = 0
        self.hits = self.misses = 0

    def get(self, key: str) -> np.ndarray | None:
        with self._lock:
            v = self._d.get(key)
            if v is None:
                self.misses += 1
                return None
            self._d.move_to_end(key)
            if self.shared is not None:
                self.shared._order.move_to_end((id(self), key))
            self.hits += 1
            return v

    def put(self, key: str, value: np.ndarray) -> None:
        with self._lock:
            if key in self._d:
                return
            self._d[key] = value
            self.bytes += value.nbytes
            sh = self.shared
            if sh is not None:
                sh._order[(id(self), key)] = weakref.ref(self)
                sh.bytes += value.nbytes
            while self.bytes > self.max_bytes and self._d:
                self._drop(next(iter(self._d)))
            while sh is not None and sh.bytes > sh.max_bytes and sh._order:
                (cid, k), ref = next(iter(sh._order.items()))
                owner = ref()
                if owner is None:       # not expected: a cache that goes away takes its blocks out first
                    del sh._order[(cid, k)]
                    sh.bytes = sum(c.bytes for r in {*sh._order.values()} if (c := r()) is not None)
                else:
                    owner._drop(k)

    def _drop(self, key: str) -> None:
        """Forget one block (caller holds the lock)."""
        old = self._d.pop(key)
        self.bytes -= old.nbytes
        if self.shared is not None:
            del self.shared._order[(id(self), key)]
            self.shared.bytes -= old.nbytes

    def clear(self) -> None:
        with self._lock:
            for k in list(self._d):
                self._drop(k)

    def __del__(self):
        # an episode let go (evicted, deleted): its blocks stop counting against the shared budget
        if getattr(self, "shared", None) is not None and self._d:
            with self._lock:
                for k, v in self._d.items():
                    self.shared._order.pop((id(self), k), None)
                    self.shared.bytes -= v.nbytes
                self._d.clear()

    def __len__(self):
        return len(self._d)


@dataclass
class PreviewResult:
    audio: np.ndarray
    start: int           # timeline sample of audio[0]
    seconds: float       # wall time
    blocks: int
    rendered: int        # blocks that were cache misses


class Previewer:
    def __init__(self, renderer: Renderer, cache: SegmentCache | None = None, block_s: float = 2.0):
        self.renderer = renderer
        self.cache = cache if cache is not None else SegmentCache()
        self.block_s = block_s

    def render(self, tl: Timeline, a: int, b: int) -> PreviewResult:
        t_start = time.perf_counter()
        a, b = max(a, 0), min(b, tl.length)
        blk = int(self.block_s * tl.sample_rate)
        parts, rendered = [], 0
        g0 = (a // blk) * blk
        for s in range(g0, b, blk):
            e = s + blk
            key = self.renderer.range_key(tl, s, e)
            y = self.cache.get(key)
            if y is None:
                y = self.renderer.render(tl, s, e)
                self.cache.put(key, y)
                rendered += 1
            parts.append(y)
        audio = np.concatenate(parts)[a - g0:b - g0] if parts else np.zeros((0, self.renderer.settings.channels), np.float32)
        return PreviewResult(audio, a, time.perf_counter() - t_start, len(parts), rendered)

    def around(self, tl: Timeline, t: int, ctx_s: float = 5.0) -> PreviewResult:
        c = int(ctx_s * tl.sample_rate)
        return self.render(tl, t - c, t + c)

    def ab(self, before: Timeline, after: Timeline, t_before: int, t_after: int,
           ctx_s: float = 5.0) -> tuple[PreviewResult, PreviewResult]:
        """Before/after pair around the same edit (positions given in each timeline)."""
        return self.around(before, t_before, ctx_s), self.around(after, t_after, ctx_s)
