"""One memory budget over every episode's listening cache (lacuna_core/preview.py SharedBudget, batch 10):
the load test showed ~200 MB kept per show listened through, until a restart."""
from __future__ import annotations

import gc
import threading

import numpy as np

from lacuna_app.episode import PREVIEW_BUDGET
from lacuna_core.preview import SegmentCache, SharedBudget


def block(n: int = 100) -> np.ndarray:
    return np.zeros(n, np.float32)          # 400 bytes


def test_the_least_recently_used_block_of_any_cache_goes_first():
    sh = SharedBudget(3 * 400)
    a, b = SegmentCache(10_000, sh), SegmentCache(10_000, sh)
    a.put("1", block())
    b.put("1", block())
    a.put("2", block())
    assert a.get("1") is not None          # a/1 is now newer than b/1
    b.put("2", block())                    # over budget: b/1 is the oldest anywhere
    assert b.get("1") is None and a.get("1") is not None and a.get("2") is not None
    assert sh.bytes == 3 * 400 == a.bytes + b.bytes


def test_each_cache_keeps_its_own_limit_too():
    sh = SharedBudget(10_000)
    a = SegmentCache(2 * 400, sh)
    for k in "123":
        a.put(k, block())
    assert len(a) == 2 and a.get("1") is None and sh.bytes == 800


def test_a_cache_let_go_frees_its_share():
    sh = SharedBudget(10_000)
    a, b = SegmentCache(10_000, sh), SegmentCache(10_000, sh)
    a.put("1", block())
    b.put("1", block())
    del a
    gc.collect()
    assert sh.bytes == 400 and len(sh._order) == 1
    b.clear()
    assert sh.bytes == 0 and not sh._order


def test_parallel_use_stays_consistent():
    sh = SharedBudget(20 * 400)
    caches = [SegmentCache(8 * 400, sh) for _ in range(6)]

    def work(c, seed):
        rng = np.random.default_rng(seed)
        for _ in range(2000):
            k = str(rng.integers(30))
            if c.get(k) is None:
                c.put(k, block())

    ts = [threading.Thread(target=work, args=(c, i)) for i, c in enumerate(caches)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sh.bytes == sum(c.bytes for c in caches) <= 20 * 400
    assert len(sh._order) == sum(len(c) for c in caches)
    assert all(c.bytes <= 8 * 400 for c in caches)


def test_the_server_shares_one_budget_of_a_gigabyte():
    assert PREVIEW_BUDGET.max_bytes == 1 << 30
