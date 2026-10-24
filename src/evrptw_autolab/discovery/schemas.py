"""Typed operator specification. This is not an executable solver."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OperatorFamily = Literal["destroy", "repair", "local_search", "charging", "fleet"]


class OperatorSpec(BaseModel):
    """An operator together with the physics it is allowed to assume."""

    operator_id: str
    version: str
    source_agent: str
    description: str
    operator_family: OperatorFamily
    implementation_reference: str
    required_capabilities: list[str] = Field(default_factory=list)
    forbidden_capabilities: list[str] = Field(default_factory=list)
    required_features: list[str] = Field(default_factory=list)
    hard_preconditions: list[str] = Field(default_factory=list)
    candidate_scoring_policy: str | None = None
    fallback_operator: str = "classical_default"
    source_hash: str = ""
