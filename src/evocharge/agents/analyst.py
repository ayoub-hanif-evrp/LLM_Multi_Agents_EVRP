"""Analyst agent: diagnostic → structured failure analysis."""

from __future__ import annotations

import json
from typing import Any

from evocharge.agents.model_config import AgentsConfig
from evocharge.agents.ollama_client import LLMBackend
from evocharge.agents.prompt_loader import load_prompt, prompt_hash, render_task
from evocharge.agents.schemas import AnalystInput, AnalystReport, StructuredGenerationResult
from evocharge.agents.failure_taxonomy import FAILURE_MODES
from evocharge.reproducibility import hash_mapping


def load_primitive_catalogue() -> dict[str, Any]:
    """Executable M7 catalogue (source of truth: operators.primitives)."""
    from evocharge.operators.primitives import catalogue_hash, catalogue_payload

    payload = catalogue_payload()
    return {
        **payload,
        "catalogue_hash": catalogue_hash(),
        "milestone_availability_note": (
            "Executable in Milestone 7; Coding Agent may call registered primitives only."
        ),
    }


def catalogue_hash() -> str:
    return hash_mapping(load_primitive_catalogue())


def build_analyst_input(
    diagnostic: dict[str, Any],
    *,
    dataset_summary: dict[str, object] | None = None,
    objective_summary: dict[str, object] | None = None,
    diagnostic_id: str | None = None,
) -> AnalystInput:
    objective = objective_summary or dict(diagnostic.get("objective") or {})
    observed = {
        "stagnation_iterations": diagnostic.get("stagnation_iterations"),
        "route_feature_quantiles": diagnostic.get("route_feature_quantiles"),
        "charging_feature_quantiles": diagnostic.get("charging_feature_quantiles"),
        "operator_statistics": diagnostic.get("operator_statistics"),
        "rejection_histogram": diagnostic.get("rejection_histogram"),
        "failure_modes": diagnostic.get("failure_modes"),
        "scale": diagnostic.get("scale"),
        "objective": diagnostic.get("objective"),
    }
    representative = []
    for frag in diagnostic.get("representative_route_fragments") or []:
        representative.append({"type": "route_fragment", **dict(frag)})
    for tid in diagnostic.get("representative_trace_ids") or []:
        representative.append({"type": "trace_reference", "trace_id": tid})
    taxonomy = [{"label": m, "description": m.replace("_", " ")} for m in FAILURE_MODES]
    return AnalystInput(
        diagnostic_id=diagnostic_id or str(diagnostic.get("instance_id") or "unknown"),
        diagnostic_hash=str(diagnostic.get("diagnostic_hash") or ""),
        dataset_summary=dataset_summary
        or {
            "dataset": diagnostic.get("dataset"),
            "scale": diagnostic.get("scale"),
            "instance_id": diagnostic.get("instance_id"),
            "label": "M6 anchored-agent integration diagnostic",
        },
        objective_summary=dict(objective),
        observed_metrics=observed,
        metric_availability=dict(diagnostic.get("metric_availability") or {}),
        failure_taxonomy=taxonomy,
        representative_evidence=representative,
    )


def analyst_json_schema() -> dict[str, Any]:
    return AnalystReport.model_json_schema()


def run_analyst(
    backend: LLMBackend,
    analyst_input: AnalystInput,
    config: AgentsConfig,
    *,
    retry_feedback: str | None = None,
    schema_retries_so_far: int = 0,
) -> StructuredGenerationResult:
    system = load_prompt("analyst_system.md")
    task_tmpl = load_prompt("analyst_task.md")
    user = render_task(
        task_tmpl,
        timing_note=analyst_input.timing_note,
        diagnostic_id=analyst_input.diagnostic_id,
        diagnostic_hash=analyst_input.diagnostic_hash,
        dataset_summary=json.dumps(analyst_input.dataset_summary, sort_keys=True, indent=2),
        objective_summary=json.dumps(analyst_input.objective_summary, sort_keys=True, indent=2),
        observed_metrics=json.dumps(analyst_input.observed_metrics, sort_keys=True, indent=2),
        metric_availability=json.dumps(
            analyst_input.metric_availability, sort_keys=True, indent=2
        ),
        failure_taxonomy=json.dumps(analyst_input.failure_taxonomy, sort_keys=True, indent=2),
        representative_evidence=json.dumps(
            analyst_input.representative_evidence, sort_keys=True, indent=2
        ),
    )
    if retry_feedback:
        user += (
            "\n\n## Schema correction feedback\n"
            f"{retry_feedback}\n"
            "Return corrected JSON only. Do not change the underlying evidence.\n"
        )
    return backend.generate_structured(
        role="analyst",
        system_prompt=system,
        user_prompt=user,
        json_schema=analyst_json_schema(),
        temperature=config.ollama.temperatures.analyst,
        prompt_template_hashes=[
            prompt_hash("analyst_system.md"),
            prompt_hash("analyst_task.md"),
        ],
        input_artifact_hashes=[hash_mapping(analyst_input.model_dump())],
        schema_retries_so_far=schema_retries_so_far,
    )
