"""Schemas for Milestone 9B population evolution."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CreationMode = Literal[
    "seed",
    "mutation",
    "semantic_crossover",
    "evidence_guided_revision",
    "novel_invention",
    "random_composition",
    "handcrafted_analogue",
    "noop_control",
    "baseline_random_mutation",
    "baseline_non_llm",
]


class ModificationPlan(BaseModel):
    mode: CreationMode
    rationale: str
    parent_ids: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    weakness_addressed: str | None = None


class FitnessVector(BaseModel):
    feasibility_preservation_rate: float = 0.0
    applicability_rate: float = 0.0
    valid_no_action_rate: float = 0.0
    effective_behavioral_change_rate: float = 0.0
    paired_objective_improvement: float = 0.0
    degradation_rate: float = 0.0
    runtime_overhead: float = 0.0
    operator_stability: float = 0.0
    selection_diversity: float = 0.0
    novelty: float = 0.0
    redundancy_with_handcrafted: float = 0.0
    source_complexity: float = 0.0
    # Higher is better for all after transforms applied in archive
    score_notes: list[str] = Field(default_factory=list)


class CandidateRecord(BaseModel):
    candidate_id: str
    parent_ids: list[str] = Field(default_factory=list)
    generation: int = 0
    creation_mode: CreationMode = "seed"
    hypothesis_ids: list[str] = Field(default_factory=list)
    model: str | None = None
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    source_hash: str = ""
    api_version: str = "1.1.0"
    catalogue_hash: str = ""
    freeze_hash: str = ""
    static_accepted: bool = False
    dynamic_accepted: bool = False
    metamorphic_accepted: bool = False
    evaluation_exposure: str = "none"
    fitness: FitnessVector = Field(default_factory=FitnessVector)
    rejection_reason: str | None = None
    outcome_counts: dict[str, int] = Field(default_factory=dict)
    n_changed_instances: int = 0
    is_noop: bool = False
    archived: bool = False
    modification_plan: ModificationPlan | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PopulationState(BaseModel):
    experiment_id: str
    generation: int = 0
    freeze_hash: str
    members: list[CandidateRecord] = Field(default_factory=list)
    archive: list[CandidateRecord] = Field(default_factory=list)
    rejected: list[CandidateRecord] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
