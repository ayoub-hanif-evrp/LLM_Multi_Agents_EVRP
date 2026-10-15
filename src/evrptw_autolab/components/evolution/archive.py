"""Diverse archive of component bundles with panel provenance."""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from evrptw_autolab.components.evolution.fitness import (
    PanelEvaluation,
    compare_panel,
    panel_is_better,
)
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES


@dataclass
class ComponentAttribution:
    """Per-component provenance for one archive member."""

    kind: str
    agent_role: str
    model: str = ""
    generated_source_hash: str = ""
    executed_source_hash: str = ""
    mutation_accepted: bool = False
    fallback_applied: bool = False
    human_default_used: bool = False
    successful_repair: bool = False
    llm_generated: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BundleCandidate:
    """One archive member: sources + panel evaluation + provenance."""

    candidate_id: str
    sources: dict[str, str]
    owners: dict[str, str]
    generation: int
    parent_ids: list[str] = field(default_factory=list)
    # Panel-level status (never confuse with a single-instance feasible flag).
    panel: dict[str, Any] = field(default_factory=dict)
    instances_tested: int = 0
    instances_feasible: int = 0
    feasibility_rate: float = 0.0
    fully_feasible_on_panel: bool = False
    candidate_validation_status: str = "unknown"
    # Deprecated single-instance fields retained for checkpoint compatibility.
    feasible: bool = False
    objective_key: list[float] = field(default_factory=list)
    runtime_s: float = 0.0
    fitness: float = float("-inf")
    llm_generated: bool = False
    genuine_llm_components: int = 0
    attribution_category: str = "pure_classical"
    model: str = ""
    tokens: int = 0
    source_hashes: dict[str, str] = field(default_factory=dict)
    component_attribution: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        payload = json.dumps(self.sources, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]

    def panel_evaluation(self) -> PanelEvaluation | None:
        if not self.panel:
            return None
        from evrptw_autolab.components.evolution.fitness import InstanceEval

        rows = [
            InstanceEval(
                family=str(r["family"]),
                instance_id=str(r["instance_id"]),
                seed=int(r["seed"]),
                feasible=bool(r["feasible"]),
                objective_key=tuple(float(x) for x in r.get("objective_key") or ()),
                runtime_s=float(r.get("runtime_s") or 0.0),
                fault_family=str(r.get("fault_family") or ""),
                fault_detail=str(r.get("fault_detail") or ""),
                vehicles=int(r.get("vehicles") or 0),
                distance=float(r.get("distance") or 0.0),
            )
            for r in self.panel.get("per_instance") or []
        ]
        return PanelEvaluation(
            instances_tested=int(self.panel.get("instances_tested") or self.instances_tested),
            instances_feasible=int(self.panel.get("instances_feasible") or self.instances_feasible),
            feasibility_rate=float(self.panel.get("feasibility_rate") or self.feasibility_rate),
            fully_feasible_on_panel=bool(
                self.panel.get("fully_feasible_on_panel")
                if "fully_feasible_on_panel" in self.panel
                else self.fully_feasible_on_panel
            ),
            total_runtime_s=float(self.panel.get("total_runtime_s") or self.runtime_s),
            validation_ok=bool(self.panel.get("validation_ok", True)),
            per_instance=rows,
            per_variant=dict(self.panel.get("per_variant") or {}),
        )


def apply_panel(candidate: BundleCandidate, panel: PanelEvaluation, *, validation_status: str) -> None:
    candidate.panel = panel.as_dict()
    candidate.instances_tested = panel.instances_tested
    candidate.instances_feasible = panel.instances_feasible
    candidate.feasibility_rate = panel.feasibility_rate
    candidate.fully_feasible_on_panel = panel.fully_feasible_on_panel
    candidate.candidate_validation_status = validation_status
    candidate.runtime_s = panel.total_runtime_s
    # `feasible` means fully feasible on the recorded panel, not a single instance.
    candidate.feasible = bool(panel.fully_feasible_on_panel and panel.validation_ok)
    if panel.per_instance:
        # Keep a representative objective_key from the first feasible row for display only.
        for row in panel.per_instance:
            if row.feasible:
                candidate.objective_key = list(row.objective_key)
                break
        else:
            candidate.objective_key = list(panel.per_instance[0].objective_key)


def classify_attribution(attr_rows: list[dict[str, Any]], sources: dict[str, str]) -> tuple[str, int]:
    """Return (category, genuine_llm_component_count)."""
    genuine = 0
    any_fallback = False
    for row in attr_rows:
        if row.get("llm_generated") and not row.get("human_default_used") and not row.get("fallback_applied"):
            genuine += 1
        if row.get("fallback_applied") or row.get("human_default_used"):
            any_fallback = True
    if genuine == 0 and all(
        sources.get(str(k), "").strip() == DEFAULT_SOURCES[k].strip() for k in DEFAULT_SOURCES
    ):
        return "pure_classical", 0
    if genuine == 0 and any_fallback:
        return "fallback_assisted", 0
    if genuine == 0:
        return "failed_generation", 0
    return "hybrid_llm", genuine


@dataclass
class CandidateArchive:
    """Fixed-capacity archive with diversity on source fingerprints."""

    capacity: int = 10
    members: list[BundleCandidate] = field(default_factory=list)
    # Cumulative budget counters restored on resume.
    llm_calls: int = 0
    llm_tokens: int = 0
    wall_s: float = 0.0

    def best(self) -> BundleCandidate | None:
        """Best fully-feasible-on-panel member; else None (never promote partial as best_feasible)."""
        feasible = [m for m in self.members if m.fully_feasible_on_panel and m.candidate_validation_status == "ok"]
        if not feasible:
            return None
        best = feasible[0]
        for member in feasible[1:]:
            pa = member.panel_evaluation()
            pb = best.panel_evaluation()
            if pa is not None and pb is not None and panel_is_better(pa, pb):
                best = member
            elif pa is not None and pb is None:
                best = member
        return best

    def best_overall(self) -> BundleCandidate | None:
        """Best member by panel comparison even if not fully feasible (for diagnostics)."""
        if not self.members:
            return None
        best = self.members[0]
        for member in self.members[1:]:
            pa = member.panel_evaluation()
            pb = best.panel_evaluation()
            if pa is not None and pb is not None and panel_is_better(pa, pb):
                best = member
        return best

    def add(self, candidate: BundleCandidate) -> bool:
        fp = candidate.fingerprint()
        for i, member in enumerate(self.members):
            if member.fingerprint() == fp:
                pa = candidate.panel_evaluation()
                pb = member.panel_evaluation()
                if pa is not None and pb is not None and panel_is_better(pa, pb):
                    self.members[i] = candidate
                    return True
                return False
        if len(self.members) < self.capacity:
            self.members.append(candidate)
            return True
        # Evict worst by panel comparison (prefer keeping fully feasible).
        worst_idx = 0
        for i in range(1, len(self.members)):
            wa = self.members[worst_idx].panel_evaluation()
            wb = self.members[i].panel_evaluation()
            if wa is None:
                worst_idx = i
                continue
            if wb is not None and compare_panel(wb, wa) > 0:
                # wb worse than wa
                worst_idx = i
            elif not self.members[i].fully_feasible_on_panel and self.members[worst_idx].fully_feasible_on_panel:
                worst_idx = i
        worst = self.members[worst_idx]
        pa = candidate.panel_evaluation()
        pw = worst.panel_evaluation()
        if pa is not None and pw is not None and panel_is_better(pa, pw):
            self.members[worst_idx] = candidate
            return True
        if candidate.fully_feasible_on_panel and not worst.fully_feasible_on_panel:
            self.members[worst_idx] = candidate
            return True
        return False

    def select_parents(self, rng: random.Random, k: int = 2) -> list[BundleCandidate]:
        """Tournament selection using panel comparison (not scalar fitness)."""
        if not self.members:
            return []
        picks: list[BundleCandidate] = []
        for _ in range(min(k, len(self.members))):
            a = rng.choice(self.members)
            b = rng.choice(self.members)
            pa, pb = a.panel_evaluation(), b.panel_evaluation()
            if pa is not None and pb is not None and panel_is_better(pb, pa):
                picks.append(b)
            else:
                picks.append(a)
        return picks

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "capacity": self.capacity,
            "llm_calls": self.llm_calls,
            "llm_tokens": self.llm_tokens,
            "wall_s": self.wall_s,
            "members": [asdict(m) for m in self.members],
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> CandidateArchive:
        data = json.loads(path.read_text(encoding="utf-8"))
        archive = cls(capacity=int(data.get("capacity", 10)))
        archive.llm_calls = int(data.get("llm_calls") or 0)
        archive.llm_tokens = int(data.get("llm_tokens") or 0)
        archive.wall_s = float(data.get("wall_s") or 0.0)
        for raw in data.get("members", []):
            # Drop unknown keys from older checkpoints if schema drifts.
            known = set(BundleCandidate.__dataclass_fields__)
            filtered = {k: v for k, v in raw.items() if k in known}
            archive.members.append(BundleCandidate(**filtered))
        return archive


def hash_sources(sources: dict[str, str]) -> dict[str, str]:
    return {str(k): hashlib.sha256(v.encode("utf-8")).hexdigest()[:16] for k, v in sources.items()}


def source_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]
