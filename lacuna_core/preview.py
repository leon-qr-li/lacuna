"""Localized preview: render only [t - ctx, t + ctx] of a timeline, with a segment cache.

The window is rendered as fixed blocks on an absolute grid. Each block is cached under
`Renderer.range_key` (a hash of exactly the content that affects that block), so:
* an edit far away leaves the key - and the cached audio - untouched;
* an upstream cut that shifts material into a block changes its key (no stale audio);
* undo returns to keys that are still cached.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np

from .edl import Timeline
from .render import Renderer


class SegmentCache:
    """In-memory LRU with a byte budget."""

    def __init__(self, max_bytes: int = 256 << 20):
        self.max_bytes = max_bytes
        self._d: OrderedDict[str, np.ndarray] = OrderedDict()
        self.bytes = 0
        self.hits = self.misses = 0

    def get(self, key: str) -> np.ndarray | None:
        v = self._d.get(key)
        if v is None:
            self.misses += 1
            return None
        self._d.move_to_end(key)
        self.hits += 1
        return v

    def put(self, key: str, value: np.ndarray) -> None:
        if key in self._d:
            return
        self._d[key] = value
        self.bytes += value.nbytes
        while self.bytes > self.max_bytes and self._d:
            _, old = self._d.popitem(last=False)
            self.bytes -= old.nbytes

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

    def around(self, tl: Timeline, t: int, ctx_s: float = 10.0) -> PreviewResult:
        c = int(ctx_s * tl.sample_rate)
        return self.render(tl, t - c, t + c)

    def ab(self, before: Timeline, after: Timeline, t_before: int, t_after: int,
           ctx_s: float = 10.0) -> tuple[PreviewResult, PreviewResult]:
        """Before/after pair around the same edit (positions given in each timeline)."""
        return self.around(before, t_before, ctx_s), self.around(after, t_after, ctx_s)
