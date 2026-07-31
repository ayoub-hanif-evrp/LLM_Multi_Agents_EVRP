"""JSONL experiment tracing with streaming flush (memory-efficient)."""

from __future__ import annotations

import gzip
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO


@dataclass
class TraceWriter:
    path: Path
    start_time: float = field(default_factory=time.perf_counter)
    _buffer: list[dict[str, Any]] = field(default_factory=list)
    flush_every: int = 20
    _handle: TextIO | None = None
    event_count: int = 0

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if str(self.path).endswith(".gz"):
            self._handle = gzip.open(self.path, "at", encoding="utf-8")
        else:
            self._handle = self.path.open("a", encoding="utf-8")

    def log(self, event: dict[str, Any]) -> None:
        if self._handle is None:
            self.open()
        payload = {
            "event_id": f"e{self.event_count:06d}",
            "t": time.perf_counter() - self.start_time,
            **event,
        }
        self.event_count += 1
        self._buffer.append(payload)
        if len(self._buffer) >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        if self._handle is None:
            self.open()
        assert self._handle is not None
        for rec in self._buffer:
            self._handle.write(json.dumps(rec, sort_keys=True) + "\n")
        self._handle.flush()
        self._buffer.clear()

    def close(self) -> None:
        self.flush()
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def read_trace_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if str(path).endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
    else:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
    return events
