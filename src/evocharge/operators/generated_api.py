"""Bounded generated-operator API types (Milestone 9A)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from evocharge.domain.instance import Instance
from evocharge.domain.solution import Solution

API_VERSION = "1.1.0"

EntityType = Literal[
    "customer", "segment", "route", "station", "insertion_position"
]


class EntityCandidate(BaseModel):
    entity_type: EntityType
    entity_id: str
    route_index: int | None = None
    start_index: int | None = None
    end_index: int | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class EntityReference(BaseModel):
    """Selected entity with optional route span (no hardcoded IDs in source)."""

    entity_type: EntityType
    entity_id: str
    route_index: int | None = None
    start_index: int | None = None
    end_index: int | None = None


class SelectionEvidence(BaseModel):
    """Why a selected entity satisfies the hypothesis (query-grounded)."""

    entity_id: str
    query_id: str
    score: float
    rationale: str = ""


class PlanAction(BaseModel):
    action_id: str
    primitive_id: str
    arguments: dict[str, object] = Field(default_factory=dict)
    rationale: str = ""


# User-facing alias for Milestone 9A wording
PrimitiveAction = PlanAction


class OperatorPlan(BaseModel):
    """Plan returned by build_operator_plan (API 1.1.0).

    When required preconditions are absent, set applicable=False with a
    no_action_reason and empty actions. Nonempty actions without selection
    evidence are rejected by semantic verification.
    """

    plan_version: str = "1.1.0"
    applicable: bool = True
    no_action_reason: str | None = None
    preconditions_checked: list[str] = Field(default_factory=list)
    selected_entities: list[EntityReference] = Field(default_factory=list)
    selection_evidence: list[SelectionEvidence] = Field(default_factory=list)
    actions: list[PlanAction] = Field(default_factory=list)
    expected_behavioral_effect: str = ""
    notes: list[str] = Field(default_factory=list)
    estimated_removals: int = 0


@dataclass(frozen=True, slots=True)
class ReadOnlySearchState:
    """Frozen view of the current search solution for plan builders."""

    solution: Solution
    instance: Instance
    unserved_customers: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class RandomSource:
    """Thin deterministic RNG wrapper for generated operators."""

    def __init__(self, seed: int = 0) -> None:
        import random

        self._rng = random.Random(seed)

    def random(self) -> float:
        return self._rng.random()

    def randint(self, a: int, b: int) -> int:
        return self._rng.randint(a, b)

    def choice(self, seq: list[Any]) -> Any:
        return self._rng.choice(seq)

    def sample(self, population: list[Any], k: int) -> list[Any]:
        return self._rng.sample(population, k)


SCORE_FUNCTION_NAME = "score_entities"
PLAN_FUNCTION_NAME = "build_operator_plan"

SCORE_SIGNATURE = (
    "def score_entities(context: OperatorContext, "
    "candidates: tuple[EntityCandidate, ...]) -> tuple[float, ...]:"
)
PLAN_SIGNATURE = (
    "def build_operator_plan(state: ReadOnlySearchState, "
    "context: OperatorContext, rng: RandomSource) -> OperatorPlan:"
)
