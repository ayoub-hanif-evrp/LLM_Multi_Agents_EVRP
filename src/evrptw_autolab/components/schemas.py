"""Typed multi-agent messages for component synthesis (VoltForge 2.0)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from evrptw_autolab.components.interfaces import ComponentKind


class AlgorithmPlan(BaseModel):
    """Architect output: which components to generate and why."""

    summary: str = ""
    components: list[ComponentKind] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    variant_notes: str = ""
    station_feature_schema: str = ""

    @field_validator("components", mode="before")
    @classmethod
    def _components(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


class ComponentProposal(BaseModel):
    """One agent's proposed scoring rule.

    Prefer ``expression`` (wrapped by the controller). ``code`` remains for
    legacy full-function replies and is normalized before validation.
    """

    component: ComponentKind
    owner_role: Literal["architect", "routing", "charging", "search", "critic"]
    code: str = ""
    expression: str = ""
    rationale: str = ""
    mechanism: str = ""
    feature_schema: str = ""


class FailureDiagnosis(BaseModel):
    fault_family: str = ""
    likely_component: ComponentKind | Literal["none"] = "none"
    explanation: str = ""
    counterexample: str = ""


class RepairRequest(BaseModel):
    component: ComponentKind
    error_detail: str = ""
    prior_code: str = ""
    lessons: list[str] = Field(default_factory=list)


class CandidateDecision(BaseModel):
    verdict: Literal["ACCEPT", "REVISE", "REJECT"] = "REVISE"
    reason: str = ""
    next_component: ComponentKind | Literal["none"] = "none"


class ExperimentFeedback(BaseModel):
    feasible: bool = False
    objective: float | None = None
    vehicles: int = 0
    distance: float = 0.0
    fault_family: str = ""
    detail: str = ""
    llm_calls: int = 0
