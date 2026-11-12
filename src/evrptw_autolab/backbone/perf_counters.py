"""Lightweight hot-path counters for solver diagnostics."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class PerfCounters:
    clones: int = 0
    full_evaluations: int = 0
    route_simulations: int = 0
    route_screens: int = 0
    charge_dp_calls: int = 0
    candidates_considered: int = 0
    candidates_rejected_screen: int = 0
    node_map_hits: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "clones": self.clones,
            "full_evaluations": self.full_evaluations,
            "route_simulations": self.route_simulations,
            "route_screens": self.route_screens,
            "charge_dp_calls": self.charge_dp_calls,
            "candidates_considered": self.candidates_considered,
            "candidates_rejected_screen": self.candidates_rejected_screen,
            "node_map_hits": self.node_map_hits,
        }


_COUNTERS: ContextVar[PerfCounters | None] = ContextVar("cipher_perf_counters", default=None)


def current_counters() -> PerfCounters | None:
    return _COUNTERS.get()


def bump(name: str, amount: int = 1) -> None:
    counters = _COUNTERS.get()
    if counters is None:
        return
    setattr(counters, name, int(getattr(counters, name)) + amount)


@contextmanager
def track_counters() -> Iterator[PerfCounters]:
    counters = PerfCounters()
    token = _COUNTERS.set(counters)
    try:
        yield counters
    finally:
        _COUNTERS.reset(token)
