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
from evrptw_autolab.problem.v2.features import FEATURE_SCHEMA_VERSION


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
    # Per-kind lineage surviving crossover: origin candidate, LLM flag, hashes.
    lineage: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    feature_schema: str = FEATURE_SCHEMA_VERSION

    def fingerprint(self) -> str:
        if self.feature_schema == FEATURE_SCHEMA_VERSION:
            payload = json.dumps(self.sources, sort_keys=True)
        else:
            payload = json.dumps(
                {"feature_schema": self.feature_schema, "sources": self.sources},
                sort_keys=True,
            )
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


def _feasibility_anchor(members: list[BundleCandidate]) -> BundleCandidate | None:
    """Member that currently covers the most instances. Regressions against it are rejected."""
    if not members:
        return None
    return max(members, key=lambda member: member.instances_feasible)


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


def classify_attribution(
    attr_rows: list[dict[str, Any]],
    sources: dict[str, str],
    *,
    lineage: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, int]:
    """Return (category, genuine_llm_component_count).

    Counts genuine LLM components from **executed lineage** (including inherited
    parent components), not only mutations attempted in the current generation.
    """
    lineage = lineage or {}
    genuine_kinds: set[str] = set()
    any_fallback = False
    for kind, meta in lineage.items():
        if meta.get("llm_generated") and not meta.get("human_default_used"):
            genuine_kinds.add(str(kind))
        if meta.get("fallback_applied") or meta.get("human_default_used"):
            any_fallback = True
    for row in attr_rows:
        kind = str(row.get("kind") or "")
        if row.get("llm_generated") and not row.get("human_default_used") and not row.get("fallback_applied"):
            genuine_kinds.add(kind)
        if row.get("fallback_applied") or row.get("human_default_used"):
            any_fallback = True
    genuine = len(genuine_kinds)
    if genuine == 0 and all(
        sources.get(str(k), "").strip() == DEFAULT_SOURCES[k].strip() for k in DEFAULT_SOURCES
    ):
        return "pure_classical", 0
    if genuine == 0 and any_fallback:
        return "fallback_assisted", 0
    if genuine == 0:
        return "failed_generation", 0
    return "hybrid_llm", genuine


def inherit_lineage_entry(
    parent: BundleCandidate,
    kind: str,
    *,
    source: str,
) -> dict[str, Any]:
    """Build a lineage record for a component taken from a parent (crossover)."""
    prior = dict(parent.lineage.get(kind) or {})
    is_default = source.strip() == DEFAULT_SOURCES[kind].strip() if kind in DEFAULT_SOURCES else False
    llm_flag = bool(prior.get("llm_generated")) and not is_default
    return {
        "kind": kind,
        "origin_candidate_id": prior.get("origin_candidate_id") or parent.candidate_id,
        "origin_generation": prior.get("origin_generation", parent.generation),
        "inherited_from": parent.candidate_id,
        "executed_source_hash": source_hash(source),
        "llm_generated": llm_flag,
        "human_default_used": is_default,
        "fallback_applied": bool(prior.get("fallback_applied")) and not llm_flag,
        "agent_role": prior.get("agent_role") or "",
        "model": prior.get("model") or parent.model,
    }


def lineage_from_mutation(
    *,
    kind: str,
    attr: dict[str, Any],
    candidate_id: str,
    generation: int,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "origin_candidate_id": candidate_id,
        "origin_generation": generation,
        "inherited_from": None,
        "executed_source_hash": attr.get("executed_source_hash") or source_hash(attr.get("executed_source") or ""),
        "llm_generated": bool(attr.get("llm_generated")),
        "human_default_used": bool(attr.get("human_default_used")),
        "fallback_applied": bool(attr.get("fallback_applied")),
        "agent_role": attr.get("agent_role") or "",
        "model": attr.get("model") or "",
        "mutation_accepted": bool(attr.get("mutation_accepted")),
        "successful_repair": bool(attr.get("successful_repair")),
    }


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
        anchor = _feasibility_anchor(self.members)
        if anchor is not None and candidate.instances_feasible < anchor.instances_feasible:
            candidate.metadata["archive_decision"] = "rejected_feasibility_regression"
            return False
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
