"""Coding Agent schemas and generation (Milestone 7)."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from evocharge.agents.model_config import AgentsConfig
from evocharge.agents.ollama_client import LLMBackend
from evocharge.agents.prompt_loader import load_prompt, prompt_hash, render_task
from evocharge.agents.schemas import (
    AlgorithmicHypothesis,
    StructuredGenerationResult,
)
from evocharge.operators.generated_api import API_VERSION
from evocharge.operators.primitives import catalogue_hash
from evocharge.reproducibility import hash_mapping


class CodingRequest(BaseModel):
    hypothesis_id: str
    hypothesis_hash: str
    operator_api_version: str = API_VERSION
    primitive_catalogue_hash: str
    allowed_primitives: list[str] = Field(default_factory=list)
    required_invariants: list[str] = Field(default_factory=list)
    complexity_limit: str = "O(n^2)"
    requested_operator_type: Literal["scoring", "plan_builder"] = "plan_builder"
    revision_feedback: list[str] = Field(default_factory=list)


class GeneratedOperatorMetadata(BaseModel):
    candidate_name: str
    hypothesis_id: str
    operator_type: Literal["scoring", "plan_builder"]
    used_primitives: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    expected_complexity: str
    behavioral_description: str
    test_intents: list[str] = Field(default_factory=list)
    known_risks: list[str] = Field(default_factory=list)


class CodingAgentResponse(BaseModel):
    metadata: GeneratedOperatorMetadata
    source_code: str


def coding_json_schema() -> dict[str, Any]:
    return CodingAgentResponse.model_json_schema()


def build_coding_request(
    hypothesis: AlgorithmicHypothesis,
    *,
    operator_type: Literal["scoring", "plan_builder"] = "plan_builder",
    revision_feedback: list[str] | None = None,
) -> CodingRequest:
    return CodingRequest(
        hypothesis_id=hypothesis.hypothesis_id,
        hypothesis_hash=hash_mapping(hypothesis.model_dump()),
        primitive_catalogue_hash=catalogue_hash(),
        allowed_primitives=list(hypothesis.required_primitives),
        required_invariants=list(hypothesis.invariants),
        complexity_limit=hypothesis.expected_complexity or "O(n^2)",
        requested_operator_type=operator_type,
        revision_feedback=list(revision_feedback or []),
    )


def run_coding_agent(
    backend: LLMBackend,
    request: CodingRequest,
    hypothesis: AlgorithmicHypothesis,
    config: AgentsConfig,
    *,
    schema_retries_so_far: int = 0,
) -> StructuredGenerationResult:
    system = load_prompt("coding_system.md")
    task = load_prompt("coding_task.md")
    user = render_task(
        task,
        request_json=json.dumps(request.model_dump(), indent=2, sort_keys=True),
        hypothesis_json=json.dumps(hypothesis.model_dump(), indent=2, sort_keys=True),
        revision_feedback=json.dumps(request.revision_feedback, indent=2, sort_keys=True),
    )
    return backend.generate_structured(
        role="coder",
        system_prompt=system,
        user_prompt=user,
        json_schema=coding_json_schema(),
        temperature=0.2,
        prompt_template_hashes=[
            prompt_hash("coding_system.md"),
            prompt_hash("coding_task.md"),
        ],
        input_artifact_hashes=[
            request.hypothesis_hash,
            request.primitive_catalogue_hash,
        ],
        schema_retries_so_far=schema_retries_so_far,
    )


# Safe example source for mock / documentation (plan builder) — M9A contract
SAFE_PLAN_EXAMPLE = '''def build_operator_plan(state, context, rng):
    _ = context
    _ = rng
    checked = ["has_routes", "rank_customers_by_energy_criticality"]
    if len(state.solution.routes) == 0:
        return OperatorPlan(
            applicable=False,
            no_action_reason="no_routes",
            preconditions_checked=checked,
            selected_entities=[],
            selection_evidence=[],
            actions=[],
            expected_behavioral_effect="none",
        )
    ranked = rank_customers_by_energy_criticality(state, 0, k=1)
    if len(ranked) == 0:
        return OperatorPlan(
            applicable=False,
            no_action_reason="no_customers_on_route",
            preconditions_checked=checked,
            selected_entities=[],
            selection_evidence=[],
            actions=[],
            expected_behavioral_effect="none",
        )
    chosen = ranked[0]
    cid = chosen.entity_id
    return OperatorPlan(
        applicable=True,
        no_action_reason=None,
        preconditions_checked=checked,
        selected_entities=[
            EntityReference(entity_type="customer", entity_id=cid, route_index=0)
        ],
        selection_evidence=[
            SelectionEvidence(
                entity_id=cid,
                query_id="rank_customers_by_energy_criticality",
                score=1.0,
                rationale="top_energy_critical",
            )
        ],
        actions=[
            plan_customer_removal([cid], action_id="a0"),
            plan_regret_reinsertion([cid], action_id="a1"),
        ],
        expected_behavioral_effect="customer_sequence_changed",
        estimated_removals=1,
    )
'''

SAFE_SCORE_EXAMPLE = (
    "def score_entities(context, candidates):\n"
    "    _ = context\n"
    "    scores = []\n"
    "    for i, _c in enumerate(candidates):\n"
    "        scores.append(float(len(candidates) - i))\n"
    "    return tuple(scores)\n"
)
