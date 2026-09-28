"""SLM-Evo types: patch ops, candidates, generation reports."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Focus = Literal["ROUTING", "CHARGING", "SEARCH"]
PatchAction = Literal["ADD", "REPLACE", "REMOVE"]
RoleName = Literal["architect", "routing", "charging", "search", "critic_inventor"]


@dataclass
class PatchOp:
    action: PatchAction
    symbol: str
    code: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PatchProposal:
    hypothesis: str
    ops: list[PatchOp]
    role: str = ""
    seed: int | None = None
    raw: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "hypothesis": self.hypothesis,
            "ops": [op.as_dict() for op in self.ops],
            "role": self.role,
            "seed": self.seed,
        }


@dataclass
class PanelMetrics:
    feasible: int
    total: int
    vehicles_sum: int
    distance_sum: float
    by_instance: dict[str, dict[str, Any]] = field(default_factory=dict)
    primary_fault: str = ""

    @property
    def fully_feasible(self) -> bool:
        return self.total > 0 and self.feasible == self.total

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateRecord:
    candidate_id: str
    parent_hash: str
    role: str
    focus: str
    hypothesis: str
    ops: list[dict[str, Any]]
    apply_ok: bool = False
    apply_error: str = ""
    source_hash: str = ""
    metrics: PanelMetrics | None = None
    accepted: bool = False
    reject_reason: str = ""
    experimental: bool = False
    repaired: bool = False
    path: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "parent_hash": self.parent_hash,
            "role": self.role,
            "focus": self.focus,
            "hypothesis": self.hypothesis,
            "ops": self.ops,
            "apply_ok": self.apply_ok,
            "apply_error": self.apply_error,
            "source_hash": self.source_hash,
            "metrics": None if self.metrics is None else self.metrics.as_dict(),
            "accepted": self.accepted,
            "reject_reason": self.reject_reason,
            "experimental": self.experimental,
            "repaired": self.repaired,
            "path": self.path,
        }


@dataclass
class GenerationReport:
    generation: int
    focus: str
    parent_hash: str
    candidates: list[CandidateRecord]
    beam_hashes: list[str]
    best_hash: str
    best_vehicles_sum: int
    best_distance_sum: float
    milestone_hit: bool = False
    milestone_instance: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "focus": self.focus,
            "parent_hash": self.parent_hash,
            "candidates": [c.as_dict() for c in self.candidates],
            "beam_hashes": self.beam_hashes,
            "best_hash": self.best_hash,
            "best_vehicles_sum": self.best_vehicles_sum,
            "best_distance_sum": self.best_distance_sum,
            "milestone_hit": self.milestone_hit,
            "milestone_instance": self.milestone_instance,
        }


FOCUS_CYCLE: tuple[Focus, ...] = ("ROUTING", "CHARGING", "ROUTING", "SEARCH")
ROLES: tuple[RoleName, ...] = ("architect", "routing", "charging", "search", "critic_inventor")
PANEL_IDS: tuple[str, ...] = ("c101C5", "c103C5", "r104C5", "r105C5")
UNLOCK = (
    "The current solver is feasible. Improve the lexicographic EVRPTW objective: "
    "first minimize number of vehicles, then total distance. Preserve feasibility. "
    "You choose the algorithm."
)
