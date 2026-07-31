"""Pydantic schemas for Analyst and Scientist agents (Milestone 6)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceReference(BaseModel):
    evidence_type: Literal[
        "metric",
        "quantile",
        "histogram",
        "trace_reference",
        "route_fragment",
        "contract_field",
    ]
    path: str
    observed_value: object | None = None
    interpretation: str


class FailureMechanism(BaseModel):
    name: str
    taxonomy_label: str | None = None
    description: str
    evidence: list[EvidenceReference] = Field(default_factory=list)
    confidence: float
    severity: Literal["low", "medium", "high"]
    recurrence: Literal["isolated", "occasional", "systematic", "unknown"]
    affected_search_component: Literal[
        "construction",
        "destroy",
        "repair",
        "charging_repair",
        "local_search",
        "acceptance",
        "operator_selection",
        "unknown",
    ]
    alternative_explanations: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class AnalystReport(BaseModel):
    report_version: str = "1.0.0"
    diagnostic_id: str
    diagnostic_hash: str
    executive_summary: str
    ranked_mechanisms: list[FailureMechanism] = Field(default_factory=list)
    unsupported_metrics_not_used: list[str] = Field(default_factory=list)
    contradictions_detected: list[str] = Field(default_factory=list)
    overall_confidence: float


class AnalystInput(BaseModel):
    diagnostic_id: str
    diagnostic_hash: str
    dataset_summary: dict[str, object] = Field(default_factory=dict)
    objective_summary: dict[str, object] = Field(default_factory=dict)
    observed_metrics: dict[str, object] = Field(default_factory=dict)
    metric_availability: dict[str, str] = Field(default_factory=dict)
    failure_taxonomy: list[dict[str, str]] = Field(default_factory=list)
    representative_evidence: list[dict[str, object]] = Field(default_factory=list)
    timing_note: str = (
        "Profiler timers may nest (e.g. charging_repair inside operators). "
        "Do not treat section times as additive percentages of wall-clock."
    )


class AlgorithmicHypothesis(BaseModel):
    hypothesis_id: str
    name: str
    category: Literal[
        "destroy",
        "repair",
        "charging",
        "local_search",
        "composite",
        "search_control",
    ]
    target_mechanisms: list[str] = Field(default_factory=list)
    evidence_references: list[EvidenceReference] = Field(default_factory=list)
    research_question: str
    causal_rationale: str
    proposed_mechanism: str
    required_primitives: list[str] = Field(default_factory=list)
    decision_conditions: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    expected_benefit: str
    expected_complexity: str
    transfer_rationale: str
    evaluation_plan: list[str] = Field(default_factory=list)
    potential_failure_modes: list[str] = Field(default_factory=list)
    distinction_from_existing_hypotheses: str
    falsification_condition: str
    confidence: float


class ScientistReport(BaseModel):
    report_version: str = "1.0.0"
    analyst_report_hash: str
    hypotheses: list[AlgorithmicHypothesis] = Field(default_factory=list)
    diversity_explanation: str
    unresolved_questions: list[str] = Field(default_factory=list)


class ScientistInput(BaseModel):
    analyst_report: AnalystReport
    analyst_validation_hash: str
    dataset_contract_summary: dict[str, object] = Field(default_factory=dict)
    objective_summary: dict[str, object] = Field(default_factory=dict)
    approved_primitive_catalogue: list[dict[str, object]] = Field(default_factory=list)
    hypothesis_constraints: dict[str, object] = Field(default_factory=dict)
    prior_hypothesis_summaries: list[dict[str, object]] = Field(default_factory=list)


class AnalystValidationReport(BaseModel):
    accepted: bool
    schema_valid: bool
    evidence_paths_valid: bool
    evidence_values_valid: bool
    availability_semantics_valid: bool
    prohibited_content_detected: list[str] = Field(default_factory=list)
    duplicate_mechanisms: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class HypothesisValidationReport(BaseModel):
    accepted: bool
    hypothesis_count_valid: bool
    evidence_valid: bool
    primitives_valid: bool
    invariants_present: bool
    testability_valid: bool
    diversity_valid: bool
    prohibited_content_detected: list[str] = Field(default_factory=list)
    duplicates_of_existing: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class LLMCallRecord(BaseModel):
    call_id: str
    role: str
    model: str
    request_options: dict[str, object] = Field(default_factory=dict)
    prompt_template_hashes: list[str] = Field(default_factory=list)
    input_artifact_hashes: list[str] = Field(default_factory=list)
    request_hash: str
    response_hash: str
    started_at: str
    duration_seconds: float
    schema_retries: int = 0
    success: bool
    error_type: str | None = None
    error_message: str | None = None
    ollama_metrics: dict[str, int | float | str | None] = Field(default_factory=dict)


class HumanReview(BaseModel):
    grounding_score: int
    relevance_score: int
    novelty_score: int
    testability_score: int
    diversity_score: int
    major_errors: list[str] = Field(default_factory=list)
    notes: str = ""


class SourceState(BaseModel):
    git_available: bool
    commit: str | None = None
    dirty: bool | None = None
    diff_hash: str | None = None
    source_tree_hash: str


class StructuredGenerationResult(BaseModel):
    """Result of one structured generation attempt (may be invalid)."""

    raw_text: str
    parsed: dict[str, Any] | None = None
    call_record: LLMCallRecord
    schema_error: str | None = None
