"""A small in-memory cache for results that are slow to work out and only change when new data arrives.

The caller puts what the result depends on in the key (the newest data date, the filters), so new data gives a new key. The time limit covers the
rest: a restated figure for a day already held shows up within `ttl` seconds. It is per process and is lost on restart.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any


class Memo:
    def __init__(self, size: int = 64, ttl: float = 600.0) -> None:
        self._items: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._size = size
        self._ttl = ttl

    def get(self, key: Hashable, make: Callable[[], Any]) -> Any:
        now = time.monotonic()
        with self._lock:
            hit = self._items.get(key)
            if hit is not None and now - hit[0] < self._ttl:
                self._items.move_to_end(key)
                return hit[1]
        value = make()  # outside the lock: two requests may both work it out once, which is harmless
        with self._lock:
            self._items[key] = (now, value)
            self._items.move_to_end(key)
            while len(self._items) > self._size:
                self._items.popitem(last=False)
        return value

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
