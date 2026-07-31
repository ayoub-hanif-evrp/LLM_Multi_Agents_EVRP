"""Deterministic validation for Analyst and Scientist reports."""

from __future__ import annotations

import re
from typing import Any

from evocharge.agents.model_config import AgentLimitsConfig
from evocharge.agents.schemas import (
    AnalystReport,
    AnalystValidationReport,
    HypothesisValidationReport,
    ScientistReport,
)
from evocharge.agents.failure_taxonomy import FAILURE_MODES
from evocharge.reproducibility import hash_mapping

CODE_PATTERNS = [
    re.compile(r"\bdef\s+\w+\s*\("),
    re.compile(r"\bclass\s+\w+\s*[:(]"),
    re.compile(r"\bimport\s+\w+"),
    re.compile(r"```python", re.IGNORECASE),
    re.compile(r"subprocess\."),
]
HIDDEN_PATTERNS = [
    re.compile(r"\bhidden[-_ ]?test\b", re.IGNORECASE),
    re.compile(r"\bholdout\b", re.IGNORECASE),
]
PARAM_ONLY_PATTERNS = [
    re.compile(r"increase\s+(the\s+)?(number\s+of\s+)?iterations", re.I),
    re.compile(r"change\s+(the\s+)?temperature", re.I),
    re.compile(r"adjust\s+(a\s+|the\s+)?weight", re.I),
    re.compile(r"use\s+a\s+better\s+llm", re.I),
]


def _unwrap_observed(value: object) -> object:
    if isinstance(value, dict) and "value" in value and set(value.keys()) <= {
        "value",
        "unit",
        "note",
    }:
        return value.get("value")
    return value


def build_evidence_document(diagnostic: dict[str, Any]) -> dict[str, Any]:
    """Paths may refer to diagnostic fields or prompt aliases."""
    return {
        **diagnostic,
        "representative_evidence": list(
            diagnostic.get("representative_route_fragments") or []
        ),
        "observed_metrics": {
            "stagnation_iterations": diagnostic.get("stagnation_iterations"),
            "route_feature_quantiles": diagnostic.get("route_feature_quantiles"),
            "charging_feature_quantiles": diagnostic.get("charging_feature_quantiles"),
            "operator_statistics": diagnostic.get("operator_statistics"),
            "rejection_histogram": diagnostic.get("rejection_histogram"),
            "failure_modes": diagnostic.get("failure_modes"),
            "scale": diagnostic.get("scale"),
            "objective": diagnostic.get("objective"),
        },
        # Common mis-nesting: station dependency lives under charging features
        "route_feature_quantiles": {
            **dict(diagnostic.get("route_feature_quantiles") or {}),
            "station_dependency_quantiles": (
                (diagnostic.get("charging_feature_quantiles") or {}).get(
                    "station_dependency_quantiles"
                )
            ),
            "charging_stops_quantiles": (
                (diagnostic.get("charging_feature_quantiles") or {}).get(
                    "charging_stops_quantiles"
                )
            ),
            "charging_detour_ratio_quantiles": (
                (diagnostic.get("charging_feature_quantiles") or {}).get(
                    "charging_detour_ratio_quantiles"
                )
            ),
            "energy_slack_min_quantiles": (
                (diagnostic.get("charging_feature_quantiles") or {}).get(
                    "energy_slack_min_quantiles"
                )
            ),
        },
    }


def resolve_path(payload: dict[str, Any], path: str) -> tuple[bool, object | None]:
    """Resolve dotted/indexed paths like failure_modes.0 or objective.vehicles_used."""
    cur: Any = payload
    if not path:
        return False, None
    parts = path.replace("[", ".").replace("]", "").split(".")
    for part in parts:
        if part == "":
            continue
        if isinstance(cur, dict):
            if part not in cur:
                return False, None
            cur = cur[part]
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return False, None
        else:
            return False, None
    return True, cur


def _values_close(a: object, b: object, tol: float) -> bool:
    if a is None and b is None:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        af, bf = float(a), float(b)
        if abs(af - bf) <= tol:
            return True
        scale = max(abs(af), abs(bf), 1e-12)
        return abs(af - bf) / scale <= max(tol, 1e-6)
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return all(_values_close(x, y, tol) for x, y in zip(a, b, strict=True))
    return a == b


def _text_blob(report_like: object) -> str:
    if hasattr(report_like, "model_dump"):
        return str(report_like.model_dump())
    return str(report_like)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _token_similarity(a: str, b: str) -> float:
    ta = set(_normalize_text(a).split())
    tb = set(_normalize_text(b).split())
    return _jaccard(ta, tb)


def detect_prohibited_content(text: str) -> list[str]:
    hits: list[str] = []
    for pat in CODE_PATTERNS:
        if pat.search(text):
            hits.append(f"code_pattern:{pat.pattern}")
    for pat in HIDDEN_PATTERNS:
        if pat.search(text):
            hits.append(f"hidden_pattern:{pat.pattern}")
    # Heuristic: long node sequences look like complete routes
    if re.search(r"\b([DCS]\d+\s*,\s*){8,}[DCS]\d+\b", text):
        hits.append("possible_complete_route")
    return hits


def validate_analyst_report(
    report: AnalystReport,
    *,
    diagnostic: dict[str, Any],
    limits: AgentLimitsConfig | None = None,
) -> AnalystValidationReport:
    limits = limits or AgentLimitsConfig()
    errors: list[str] = []
    warnings: list[str] = []
    prohibited = detect_prohibited_content(_text_blob(report))
    schema_valid = True
    evidence_paths_valid = True
    evidence_values_valid = True
    availability_ok = True

    if report.diagnostic_hash != diagnostic.get("diagnostic_hash"):
        errors.append("diagnostic_hash_mismatch")
        schema_valid = False

    if not (0.0 <= report.overall_confidence <= 1.0):
        errors.append("overall_confidence_out_of_range")
        schema_valid = False

    if len(report.ranked_mechanisms) > limits.max_mechanisms:
        errors.append("too_many_mechanisms")
        schema_valid = False

    availability = dict(diagnostic.get("metric_availability") or {})
    evidence_doc = build_evidence_document(diagnostic)
    names: list[str] = []
    for mech in report.ranked_mechanisms:
        names.append(_normalize_text(mech.name))
        if not (0.0 <= mech.confidence <= 1.0):
            errors.append(f"confidence_out_of_range:{mech.name}")
            schema_valid = False
        if not mech.evidence:
            errors.append(f"mechanism_without_evidence:{mech.name}")
            evidence_paths_valid = False
        if mech.taxonomy_label and mech.taxonomy_label not in FAILURE_MODES:
            errors.append(f"unknown_taxonomy_label:{mech.taxonomy_label}")
            schema_valid = False
        for ev in mech.evidence:
            root_key = ev.path.split(".")[0].split("[")[0]
            status = availability.get(root_key)
            if status == "unsupported_by_contract":
                errors.append(f"unsupported_metric_used:{ev.path}")
                availability_ok = False
                continue
            if status == "tracing_disabled":
                interp = (ev.interpretation or "").lower()
                if (
                    "no occurrence" in interp
                    or "no events" in interp
                    or "absent" in interp
                ):
                    errors.append(f"tracing_disabled_misused:{ev.path}")
                    availability_ok = False
            ok, value = resolve_path(evidence_doc, ev.path)
            if not ok:
                errors.append(f"unresolved_evidence_path:{ev.path}")
                evidence_paths_valid = False
                continue
            observed = _unwrap_observed(ev.observed_value)
            if observed is not None and not _values_close(
                observed, value, limits.evidence_value_tolerance
            ):
                errors.append(f"evidence_value_mismatch:{ev.path}")
                evidence_values_valid = False

    duplicates: list[str] = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if _token_similarity(a, b) >= 0.9:
                duplicates.append(f"{a}~{b}")
                warnings.append(f"duplicate_mechanism_wording:{a}")

    if prohibited:
        errors.extend(prohibited)

    accepted = (
        schema_valid
        and evidence_paths_valid
        and evidence_values_valid
        and availability_ok
        and not prohibited
        and not any(e.startswith("mechanism_without_evidence") for e in errors)
        and not any(e.startswith("unknown_taxonomy") for e in errors)
        and "diagnostic_hash_mismatch" not in errors
    )
    return AnalystValidationReport(
        accepted=accepted,
        schema_valid=schema_valid and "diagnostic_hash_mismatch" not in errors,
        evidence_paths_valid=evidence_paths_valid,
        evidence_values_valid=evidence_values_valid,
        availability_semantics_valid=availability_ok,
        prohibited_content_detected=prohibited,
        duplicate_mechanisms=duplicates,
        warnings=warnings,
        errors=errors,
    )


def validate_scientist_report(
    report: ScientistReport,
    *,
    analyst: AnalystReport,
    catalogue_ids: set[str],
    limits: AgentLimitsConfig | None = None,
    prior_names: list[str] | None = None,
) -> HypothesisValidationReport:
    limits = limits or AgentLimitsConfig()
    errors: list[str] = []
    warnings: list[str] = []
    prohibited = detect_prohibited_content(_text_blob(report))
    mechanism_names = {m.name for m in analyst.ranked_mechanisms}
    count_ok = len(report.hypotheses) == limits.required_hypotheses
    if not count_ok:
        errors.append(
            f"hypothesis_count:{len(report.hypotheses)}!={limits.required_hypotheses}"
        )

    evidence_ok = True
    primitives_ok = True
    invariants_ok = True
    testability_ok = True
    diversity_ok = True
    duplicates_existing: list[str] = []
    prior = {_normalize_text(n) for n in (prior_names or [])}

    for hyp in report.hypotheses:
        if not (0.0 <= hyp.confidence <= 1.0):
            errors.append(f"confidence_out_of_range:{hyp.hypothesis_id}")
        for tm in hyp.target_mechanisms:
            if tm not in mechanism_names:
                errors.append(f"unknown_target_mechanism:{tm}")
                evidence_ok = False
        if not hyp.invariants:
            errors.append(f"missing_invariants:{hyp.hypothesis_id}")
            invariants_ok = False
        if not hyp.falsification_condition.strip():
            errors.append(f"missing_falsification:{hyp.hypothesis_id}")
            testability_ok = False
        if not hyp.evaluation_plan:
            errors.append(f"missing_evaluation_plan:{hyp.hypothesis_id}")
            testability_ok = False
        if not hyp.required_primitives:
            errors.append(f"missing_primitives:{hyp.hypothesis_id}")
            primitives_ok = False
        for pid in hyp.required_primitives:
            if pid not in catalogue_ids:
                errors.append(f"unknown_primitive:{pid}")
                primitives_ok = False
        blob = " ".join(
            [
                hyp.name,
                hyp.proposed_mechanism,
                hyp.research_question,
                hyp.causal_rationale,
            ]
        )
        for pat in PARAM_ONLY_PATTERNS:
            if pat.search(blob):
                errors.append(f"parameter_only_hypothesis:{hyp.hypothesis_id}")
                diversity_ok = False
        if _normalize_text(hyp.name) in prior:
            duplicates_existing.append(hyp.name)
        for ev in hyp.evidence_references:
            # Scientist evidence may point into analyst report dump
            ok, _ = resolve_path(analyst.model_dump(), ev.path)
            if not ok:
                ok2, _ = resolve_path(
                    {"ranked_mechanisms": [m.model_dump() for m in analyst.ranked_mechanisms]},
                    ev.path,
                )
                ok = ok2
            if not ok:
                # allow referencing diagnostic-style paths already validated upstream
                warnings.append(f"scientist_evidence_path_unresolved:{ev.path}")

    # Pairwise diversity
    hyps = report.hypotheses
    for i in range(len(hyps)):
        for j in range(i + 1, len(hyps)):
            a, b = hyps[i], hyps[j]
            if a.category == b.category:
                prim_overlap = _jaccard(set(a.required_primitives), set(b.required_primitives))
                mech_overlap = _jaccard(set(a.target_mechanisms), set(b.target_mechanisms))
                text_sim = _token_similarity(
                    a.proposed_mechanism + " " + a.name,
                    b.proposed_mechanism + " " + b.name,
                )
                cond_overlap = _jaccard(
                    set(map(_normalize_text, a.decision_conditions)),
                    set(map(_normalize_text, b.decision_conditions)),
                )
                if (
                    prim_overlap >= limits.diversity_primitive_overlap_max
                    and mech_overlap >= limits.diversity_mechanism_overlap_max
                    and text_sim >= limits.diversity_text_similarity_max
                ):
                    errors.append(f"hypotheses_too_similar:{a.hypothesis_id},{b.hypothesis_id}")
                    diversity_ok = False
                elif text_sim >= 0.95 and cond_overlap >= 0.9:
                    errors.append(f"hypotheses_near_duplicate:{a.hypothesis_id},{b.hypothesis_id}")
                    diversity_ok = False

    if prohibited:
        errors.extend(prohibited)

    accepted = (
        count_ok
        and evidence_ok
        and primitives_ok
        and invariants_ok
        and testability_ok
        and diversity_ok
        and not prohibited
        and not duplicates_existing
        and not any(e.startswith("parameter_only") for e in errors)
    )
    return HypothesisValidationReport(
        accepted=accepted,
        hypothesis_count_valid=count_ok,
        evidence_valid=evidence_ok,
        primitives_valid=primitives_ok,
        invariants_present=invariants_ok,
        testability_valid=testability_ok,
        diversity_valid=diversity_ok,
        prohibited_content_detected=prohibited,
        duplicates_of_existing=duplicates_existing,
        warnings=warnings,
        errors=errors,
    )


def validation_hash(report: AnalystValidationReport | HypothesisValidationReport) -> str:
    return hash_mapping(report.model_dump())
