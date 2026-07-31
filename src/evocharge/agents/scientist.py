"""Scientist agent: validated Analyst report → algorithmic hypotheses."""

from __future__ import annotations

import json
from typing import Any

from evocharge.agents.analyst import load_primitive_catalogue
from evocharge.agents.model_config import AgentsConfig
from evocharge.agents.ollama_client import LLMBackend
from evocharge.agents.prompt_loader import load_prompt, prompt_hash, render_task
from evocharge.agents.schemas import (
    AnalystReport,
    ScientistInput,
    ScientistReport,
    StructuredGenerationResult,
)
from evocharge.reproducibility import hash_mapping


def build_scientist_input(
    analyst_report: AnalystReport,
    *,
    analyst_validation_hash: str,
    dataset_contract_summary: dict[str, object] | None = None,
    objective_summary: dict[str, object] | None = None,
    prior_hypothesis_summaries: list[dict[str, object]] | None = None,
    required_hypotheses: int = 3,
) -> ScientistInput:
    catalogue = load_primitive_catalogue()
    return ScientistInput(
        analyst_report=analyst_report,
        analyst_validation_hash=analyst_validation_hash,
        dataset_contract_summary=dataset_contract_summary or {},
        objective_summary=objective_summary or {},
        approved_primitive_catalogue=list(catalogue.get("primitives") or []),
        hypothesis_constraints={
            "required_hypotheses": required_hypotheses,
            "no_code": True,
            "no_parameter_only_tweaks": True,
            "primitives_must_be_from_catalogue": True,
        },
        prior_hypothesis_summaries=prior_hypothesis_summaries or [],
    )


def scientist_json_schema() -> dict[str, Any]:
    return ScientistReport.model_json_schema()


def run_scientist(
    backend: LLMBackend,
    scientist_input: ScientistInput,
    config: AgentsConfig,
    *,
    retry_feedback: str | None = None,
    schema_retries_so_far: int = 0,
) -> StructuredGenerationResult:
    system = load_prompt("scientist_system.md")
    task_tmpl = load_prompt("scientist_task.md")
    user = render_task(
        task_tmpl,
        analyst_validation_hash=scientist_input.analyst_validation_hash,
        analyst_report=json.dumps(
            scientist_input.analyst_report.model_dump(), sort_keys=True, indent=2
        ),
        dataset_contract_summary=json.dumps(
            scientist_input.dataset_contract_summary, sort_keys=True, indent=2
        ),
        objective_summary=json.dumps(
            scientist_input.objective_summary, sort_keys=True, indent=2
        ),
        approved_primitive_catalogue=json.dumps(
            scientist_input.approved_primitive_catalogue, sort_keys=True, indent=2
        ),
        hypothesis_constraints=json.dumps(
            scientist_input.hypothesis_constraints, sort_keys=True, indent=2
        ),
        prior_hypothesis_summaries=json.dumps(
            scientist_input.prior_hypothesis_summaries, sort_keys=True, indent=2
        ),
    )
    if retry_feedback:
        user += (
            "\n\n## Schema correction feedback\n"
            f"{retry_feedback}\n"
            "Return corrected JSON only. Do not alter the Analyst evidence.\n"
        )
    return backend.generate_structured(
        role="scientist",
        system_prompt=system,
        user_prompt=user,
        json_schema=scientist_json_schema(),
        temperature=config.ollama.temperatures.scientist,
        prompt_template_hashes=[
            prompt_hash("scientist_system.md"),
            prompt_hash("scientist_task.md"),
        ],
        input_artifact_hashes=[hash_mapping(scientist_input.model_dump())],
        schema_retries_so_far=schema_retries_so_far,
    )
