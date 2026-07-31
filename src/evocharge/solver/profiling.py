"""Lightweight section profiler for solver components."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Profiler:
    """Thread-safe cumulative timers and counters."""

    _times: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @contextmanager
    def section(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            with self._lock:
                self._times[name] += elapsed
                self._counts[name] += 1

    def add(self, name: str, seconds: float) -> None:
        with self._lock:
            self._times[name] += seconds
            self._counts[name] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "times_seconds": dict(sorted(self._times.items())),
                "counts": dict(sorted(self._counts.items())),
                "mean_seconds": {
                    k: (self._times[k] / self._counts[k] if self._counts[k] else 0.0)
                    for k in sorted(self._times)
                },
            }

    def merge(self, other: Profiler) -> None:
        snap = other.snapshot()
        with self._lock:
            for k, v in snap["times_seconds"].items():
                self._times[k] += float(v)
            for k, v in snap["counts"].items():
                self._counts[k] += int(v)
