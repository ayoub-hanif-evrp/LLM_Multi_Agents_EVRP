"""Memory helpers and workstation limits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psutil


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    rss_bytes: int
    available_bytes: int
    percent: float


def current_memory() -> MemorySnapshot:
    proc = psutil.Process()
    vm = psutil.virtual_memory()
    return MemorySnapshot(
        rss_bytes=int(proc.memory_info().rss),
        available_bytes=int(vm.available),
        percent=float(vm.percent),
    )


def memory_dict() -> dict[str, Any]:
    snap = current_memory()
    return {
        "rss_bytes": snap.rss_bytes,
        "rss_mb": snap.rss_bytes / (1024 * 1024),
        "available_bytes": snap.available_bytes,
        "available_mb": snap.available_bytes / (1024 * 1024),
        "system_percent": snap.percent,
    }


def recommend_workers(max_workers: int = 4, min_available_mb: float = 1500.0) -> int:
    """Reduce workers when available RAM is low (16GB workstation defaults)."""
    available_mb = current_memory().available_bytes / (1024 * 1024)
    if available_mb < min_available_mb:
        return 1
    if available_mb < min_available_mb * 2:
        return min(2, max_workers)
    return max(1, min(max_workers, 4))
