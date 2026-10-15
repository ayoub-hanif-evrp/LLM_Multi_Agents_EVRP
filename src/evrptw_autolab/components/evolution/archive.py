"""Diverse archive of component bundles with provenance."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from evrptw_autolab.components.interfaces import ComponentKind


@dataclass
class BundleCandidate:
    """One archive member: sources + measured fitness + provenance."""

    candidate_id: str
    sources: dict[str, str]
    owners: dict[str, str]
    generation: int
    parent_ids: list[str] = field(default_factory=list)
    feasible: bool = False
    objective_key: list[float] = field(default_factory=list)
    runtime_s: float = 0.0
    fitness: float = float("-inf")
    llm_generated: bool = False
    model: str = ""
    tokens: int = 0
    source_hashes: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        payload = json.dumps(self.sources, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


@dataclass
class CandidateArchive:
    """Fixed-capacity archive with diversity on source fingerprints."""

    capacity: int = 10
    members: list[BundleCandidate] = field(default_factory=list)

    def best(self) -> BundleCandidate | None:
        feasible = [m for m in self.members if m.feasible]
        pool = feasible or self.members
        if not pool:
            return None
        return max(pool, key=lambda m: m.fitness)

    def add(self, candidate: BundleCandidate) -> bool:
        fp = candidate.fingerprint()
        if any(m.fingerprint() == fp for m in self.members):
            # Replace only if strictly better fitness.
            for i, member in enumerate(self.members):
                if member.fingerprint() == fp and candidate.fitness > member.fitness:
                    self.members[i] = candidate
                    return True
            return False
        if len(self.members) < self.capacity:
            self.members.append(candidate)
            return True
        # Evict worst infeasible first, else worst fitness.
        worst_idx = min(
            range(len(self.members)),
            key=lambda i: (
                self.members[i].feasible,
                self.members[i].fitness,
            ),
        )
        if candidate.fitness > self.members[worst_idx].fitness or (
            candidate.feasible and not self.members[worst_idx].feasible
        ):
            self.members[worst_idx] = candidate
            return True
        return False

    def select_parents(self, rng, k: int = 2) -> list[BundleCandidate]:
        if not self.members:
            return []
        weights = [max(1e-6, m.fitness + 1.0) for m in self.members]
        total = sum(weights)
        picks: list[BundleCandidate] = []
        for _ in range(min(k, len(self.members))):
            r = rng.random() * total
            acc = 0.0
            for member, w in zip(self.members, weights, strict=True):
                acc += w
                if r <= acc:
                    picks.append(member)
                    break
        return picks

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "capacity": self.capacity,
            "members": [asdict(m) for m in self.members],
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> CandidateArchive:
        data = json.loads(path.read_text(encoding="utf-8"))
        archive = cls(capacity=int(data.get("capacity", 10)))
        for raw in data.get("members", []):
            archive.members.append(BundleCandidate(**raw))
        return archive


def hash_sources(sources: dict[ComponentKind | str, str]) -> dict[str, str]:
    return {
        str(k): hashlib.sha256(v.encode("utf-8")).hexdigest()[:16] for k, v in sources.items()
    }
