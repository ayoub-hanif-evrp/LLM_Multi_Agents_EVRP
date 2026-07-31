from __future__ import annotations

from typing import Protocol

from evocharge.distances.euclidean import arc_metrics as euclidean_arc_metrics
from evocharge.domain.arc import ArcMetrics
from evocharge.domain.instance import Instance


class DistanceProvider(Protocol):
    def metrics(self, instance: Instance, from_id: str, to_id: str) -> ArcMetrics: ...


class EuclideanDistanceProvider:
    def metrics(self, instance: Instance, from_id: str, to_id: str) -> ArcMetrics:
        return euclidean_arc_metrics(instance, from_id, to_id)


def default_provider() -> EuclideanDistanceProvider:
    return EuclideanDistanceProvider()
