from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from evocharge.domain.route import Route


@dataclass(frozen=True, slots=True)
class Solution:
    routes: tuple[Route, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def all_node_visits(self) -> tuple[str, ...]:
        visits: list[str] = []
        for route in self.routes:
            visits.extend(route.node_ids)
        return tuple(visits)
