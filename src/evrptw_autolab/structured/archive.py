"""Population archive for structured synthesis (elites + diverse + newest)."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from evrptw_autolab.evolution.evaluate import code_hash
from evrptw_autolab.structured.fitness import fitness_key


@dataclass
class ArchiveMember:
    source: str
    code_hash: str
    fitness: tuple
    info: dict[str, Any] = field(default_factory=dict)
    generation: int = 0
    failure_family: str = ""


class Population:
    """Fixed-size archive of distinct solver hashes."""

    def __init__(self, archive_size: int = 8) -> None:
        self.archive_size = max(1, int(archive_size))
        self.members: list[ArchiveMember] = []

    def __len__(self) -> int:
        return len(self.members)

    def add(
        self,
        source: str,
        info: dict[str, Any] | None = None,
        *,
        generation: int = 0,
    ) -> bool:
        """Insert if hash is new. Returns False when duplicate hash rejected."""
        text = source or ""
        if not text.strip():
            return False
        digest = code_hash(text)
        if any(m.code_hash == digest for m in self.members):
            return False
        payload = dict(info or {})
        key = payload.get("fitness")
        if not isinstance(key, tuple):
            key = fitness_key(payload)
        family = str(
            (payload.get("diagnostic") or {}).get("family")
            or payload.get("category")
            or ""
        )
        self.members.append(
            ArchiveMember(
                source=text,
                code_hash=digest,
                fitness=tuple(key),
                info=payload,
                generation=int(generation),
                failure_family=family,
            )
        )
        self._trim()
        return True

    def elites(self, k: int = 2) -> list[ArchiveMember]:
        ordered = sorted(self.members, key=lambda m: m.fitness, reverse=True)
        return ordered[: max(0, k)]

    def select_parents(self, rng: random.Random, k: int = 2) -> list[ArchiveMember]:
        """Mix of elite + random archive members (with replacement if small)."""
        if not self.members:
            return []
        k = max(1, int(k))
        chosen: list[ArchiveMember] = []
        elite = self.elites(1)
        if elite:
            chosen.append(elite[0])
        while len(chosen) < k:
            chosen.append(rng.choice(self.members))
        return chosen[:k]

    def best(self) -> ArchiveMember | None:
        if not self.members:
            return None
        return max(self.members, key=lambda m: m.fitness)

    def _trim(self) -> None:
        if len(self.members) <= self.archive_size:
            return
        # Keep: top elites, diverse failure families, newest.
        by_fit = sorted(self.members, key=lambda m: m.fitness, reverse=True)
        keep: list[ArchiveMember] = []
        seen_hashes: set[str] = set()

        def _take(member: ArchiveMember) -> None:
            if member.code_hash in seen_hashes:
                return
            if len(keep) >= self.archive_size:
                return
            keep.append(member)
            seen_hashes.add(member.code_hash)

        elite_n = max(1, self.archive_size // 3)
        for member in by_fit[:elite_n]:
            _take(member)

        # Diverse by failure family (one per family not already kept).
        families_kept = {m.failure_family for m in keep if m.failure_family}
        for member in by_fit:
            if member.failure_family and member.failure_family not in families_kept:
                _take(member)
                families_kept.add(member.failure_family)

        # Newest by generation then insertion order.
        by_new = sorted(
            self.members,
            key=lambda m: (m.generation, self.members.index(m)),
            reverse=True,
        )
        for member in by_new:
            _take(member)

        # Fill remaining with next-best fitness.
        for member in by_fit:
            _take(member)

        self.members = keep
