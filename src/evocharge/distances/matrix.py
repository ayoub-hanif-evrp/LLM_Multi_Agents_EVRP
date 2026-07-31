from __future__ import annotations

from evocharge.distances.provider import DistanceProvider, default_provider
from evocharge.domain.arc import ArcMetrics
from evocharge.domain.instance import Instance


class DistanceMatrix:
    """Lazy on-demand distance cache for an instance."""

    def __init__(
        self,
        instance: Instance,
        provider: DistanceProvider | None = None,
    ) -> None:
        self.instance = instance
        self.provider = provider or default_provider()
        self._cache: dict[tuple[str, str], ArcMetrics] = {}

    def get(self, from_id: str, to_id: str) -> ArcMetrics:
        key = (from_id, to_id)
        if key not in self._cache:
            self._cache[key] = self.provider.metrics(self.instance, from_id, to_id)
        return self._cache[key]
