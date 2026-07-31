"""Critic Agent schemas and generation (Milestone 8)."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from evocharge.agents.model_config import AgentsConfig
from evocharge.agents.ollama_client import LLMBackend
from evocharge.agents.prompt_loader import load_prompt, prompt_hash, render_task
from evocharge.agents.schemas import StructuredGenerationResult


class CriticReport(BaseModel):
    candidate_id: str
    evidence_summary: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    causal_interpretation: list[str] = Field(default_factory=list)
    redundancy_assessment: str
    generalization_risks: list[str] = Field(default_factory=list)
    recommended_status: Literal[
        "reject",
        "revise_later",
        "retain_for_evolution",
        "insufficient_evidence",
    ]
    suggested_revision_targets: list[str] = Field(default_factory=list)
    unsupported_claims_avoided: list[str] = Field(default_factory=list)
    confidence: float


def critic_json_schema() -> dict[str, Any]:
    return CriticReport.model_json_schema()


def run_critic_agent(
    backend: LLMBackend,
    *,
    evaluation_summary: dict[str, Any],
    config: AgentsConfig,
    schema_retries_so_far: int = 0,
) -> StructuredGenerationResult:
    system = load_prompt("critic_system.md")
    task = load_prompt("critic_task.md")
    # Bound the payload — no unrestricted raw files
    bounded = {
        "candidate_id": evaluation_summary.get("candidate_id"),
        "category": evaluation_summary.get("category"),
        "classification": evaluation_summary.get("classification"),
        "analogue": evaluation_summary.get("analogue"),
        "paired_distance_deltas_vs_baseline": (
            evaluation_summary.get("paired_distance_deltas_vs_baseline") or []
        )[:30],
        "analogue_similarity_sign_agreement": evaluation_summary.get(
            "analogue_similarity_sign_agreement"
        ),
        "behavioral_probe_count": len(
            (evaluation_summary.get("behavioral") or {}).get("behavioral_probes") or []
        ),
        "behavioral_sample": (
            (evaluation_summary.get("behavioral") or {}).get("behavioral_probes") or []
        )[:9],
        "set_label": evaluation_summary.get("set_label"),
        "not_benchmark_claim": True,
        "optimization_claim_forbidden": True,
    }
    user = render_task(
        task,
        evaluation_json=json.dumps(bounded, indent=2, sort_keys=True),
    )
    return backend.generate_structured(
        role="critic",
        system_prompt=system,
        user_prompt=user,
        json_schema=critic_json_schema(),
        temperature=0.2,
        prompt_template_hashes=[
            prompt_hash("critic_system.md"),
            prompt_hash("critic_task.md"),
        ],
        input_artifact_hashes=[],
        schema_retries_so_far=schema_retries_so_far,
    )
