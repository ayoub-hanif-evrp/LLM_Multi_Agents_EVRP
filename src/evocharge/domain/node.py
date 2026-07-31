from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

NodeKind = Literal["depot", "customer", "station"]


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    kind: NodeKind
    coordinates: tuple[float, float] | None
    demand: float = 0.0
    service_duration: float = 0.0
    ready_time: float = 0.0
    due_time: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)
