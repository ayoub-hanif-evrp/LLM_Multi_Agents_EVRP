from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from evocharge.domain.node import Node
from evocharge.domain.vehicle import Vehicle


@dataclass(frozen=True, slots=True)
class Instance:
    instance_id: str
    dataset_name: str
    nodes: Mapping[str, Node]
    depot_id: str
    customer_ids: tuple[str, ...]
    station_ids: tuple[str, ...]
    vehicle: Vehicle
    horizon: float
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def customers(self) -> Sequence[Node]:
        return tuple(self.nodes[cid] for cid in self.customer_ids)

    def stations(self) -> Sequence[Node]:
        return tuple(self.nodes[sid] for sid in self.station_ids)

    @property
    def depot(self) -> Node:
        return self.nodes[self.depot_id]
