"""Campaign islands start at one lineage; additional islands are optional."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Island:
    island_id: int
    elite_id: str | None = None
    status: str = "active"


@dataclass
class IslandBoard:
    islands: list[Island] = field(default_factory=lambda: [Island(island_id=0)])
