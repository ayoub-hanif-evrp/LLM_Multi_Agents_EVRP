"""Milestone 6 orchestrator state machine."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evocharge.agents.analyst import (
    build_analyst_input,
    catalogue_hash,
    load_primitive_catalogue,
    run_analyst,
)
from evocharge.agents.artifacts import AgentRunStore
from evocharge.agents.model_config import AgentsConfig
from evocharge.agents.ollama_client import (
    LLMBackend,
    MockBackend,
    OllamaBackend,
    ReplayBackend,
)
from evocharge.agents.schemas import AnalystReport, ScientistReport
from evocharge.agents.scientist import build_scientist_input, run_scientist
from evocharge.agents.validation import (
    validate_analyst_report,
    validate_scientist_report,
    validation_hash,
)
from evocharge.reproducibility import hash_mapping, source_state
from evocharge.system_info import collect_system_info


def _validate_diagnostic_file(path: Path) -> dict[str, Any]:
    """Minimal diagnostic input check (full diagnostics package removed)."""
    if not path.is_file():
        return {"ok": False, "errors": [f"missing:{path}"]}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "errors": [f"json:{exc}"]}
    if not isinstance(data, dict):
        return {"ok": False, "errors": ["not_object"]}
    return {"ok": True, "errors": [], "keys": sorted(data.keys())}


class AgentOrchestrator:
    def __init__(
        self,
        *,
        project_root: Path,
        config: AgentsConfig,
        backend: LLMBackend | None = None,
        artifacts_root: Path | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.config = config
        self.artifacts_root = Path(
            artifacts_root or (self.project_root / "artifacts" / "agents")
        )
        self.backend = backend or self._default_backend()

    @staticmethod
    def _finish(store: AgentRunStore, payload: dict[str, Any]) -> dict[str, Any]:
        store.write_summary(payload)
        return payload

    def _default_backend(self) -> LLMBackend:
        kind = self.config.backend.lower()
        if kind == "mock":
            return MockBackend()
        if kind == "replay":
            if not self.config.replay_dir:
                raise ValueError("replay backend requires replay_dir")
            return ReplayBackend(Path(self.config.replay_dir))
        return OllamaBackend(self.config.ollama)

    def run_m6(
        self,
        diagnostic_path: Path,
        *,
        run_id: str | None = None,
        model: str | None = None,
        contract_path: Path | None = None,
    ) -> dict[str, Any]:
        diagnostic_path = Path(diagnostic_path)
        rid = run_id or f"m6_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
        store = AgentRunStore(self.artifacts_root, rid)
        store.record_transition("CREATED")

        # Model metadata
        if model and isinstance(self.backend, OllamaBackend):
            self.backend.model = model

        diag_validation = _validate_diagnostic_file(diagnostic_path)
        store.write_input("diagnostic_validation.json", diag_validation)
        if not diag_validation.get("ok"):
            store.record_transition("INPUT_REJECTED", diag_validation)
            summary = {
                "run_id": rid,
                "state": "INPUT_REJECTED",
                "reason": "diagnostic_validation_failed",
                "diagnostic_validation": diag_validation,
            }
            return self._finish(store, summary)

        diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
        store.write_input("diagnostic.json", diagnostic)

        contract_summary = {}
        cpath = contract_path or (
            self.project_root / "data" / "contracts" / "schneider_v1.0.json"
        )
        if cpath.is_file():
            raw_c = json.loads(cpath.read_text(encoding="utf-8"))
            contract_summary = {
                "dataset_name": raw_c.get("dataset_name"),
                "dataset_version": raw_c.get("dataset_version"),
                "contract_hash": raw_c.get("contract_hash"),
                "charging_policy": raw_c.get("charging_policy"),
                "energy_consumption_model": raw_c.get("energy_consumption_model"),
                "objective_definition": raw_c.get("objective_definition"),
                "missing_or_ambiguous_fields": raw_c.get("missing_or_ambiguous_fields"),
            }
        store.write_input("contract_summary.json", contract_summary)
        objective_summary = dict(diagnostic.get("objective") or {})
        store.write_input("objective_summary.json", objective_summary)
        catalogue = load_primitive_catalogue()
        store.write_input("primitive_catalogue.json", catalogue)

        src = source_state(self.project_root)
        env = collect_system_info(self.project_root)
        from evocharge.agents.artifacts import write_json

        write_json(store.run_dir / "environment.json", env)
        write_json(
            store.run_dir / "model.json",
            {
                "backend": self.config.backend,
                "model": getattr(self.backend, "model", self.config.ollama.model),
                "ollama": self.config.ollama.model_dump(),
                "limits": self.config.limits.model_dump(),
            },
        )
        write_json(
            store.run_dir / "run_config.json",
            {
                "run_id": rid,
                "diagnostic_path": str(diagnostic_path),
                "diagnostic_hash": diagnostic.get("diagnostic_hash"),
                "catalogue_hash": catalogue_hash(),
                "source_state": src.model_dump(),
                "label": "M6 anchored-agent integration run",
            },
        )
        store.record_transition("INPUT_VALIDATED")

        # --- Analyst ---
        a_input = build_analyst_input(
            diagnostic,
            dataset_summary={
                "dataset": diagnostic.get("dataset"),
                "scale": diagnostic.get("scale"),
                "instance_id": diagnostic.get("instance_id"),
                "coverage_label": "M6 anchored-agent integration runs",
                "families_present_note": "RC-wide and R-wide only for Cus100 anchors",
            },
            objective_summary=objective_summary,
        )
        store.write_role_json("analyst", "request.json", a_input.model_dump())
        store.record_transition("ANALYST_REQUESTED")

        analyst_report: AnalystReport | None = None
        a_val = None
        retries = 0
        feedback = None
        last_result = None
        while True:
            result = run_analyst(
                self.backend,
                a_input,
                self.config,
                retry_feedback=feedback,
                schema_retries_so_far=retries,
            )
            last_result = result
            store.write_role_text("analyst", "raw_response.txt", result.raw_text)
            store.write_role_json(
                "analyst", "call_record.json", result.call_record.model_dump()
            )
            if result.call_record.error_type in {
                "timeout",
                "transport_error",
                "http_error",
            }:
                store.record_transition(
                    "ANALYST_TRANSPORT_FAILED",
                    {"error": result.call_record.error_message},
                )
                summary = {
                    "run_id": rid,
                    "state": "ANALYST_TRANSPORT_FAILED",
                    "call_record": result.call_record.model_dump(),
                }
                return self._finish(store, summary)
            if result.parsed is None:
                if retries < self.config.ollama.max_schema_retries:
                    retries += 1
                    feedback = result.schema_error or "Invalid JSON"
                    continue
                store.write_role_json(
                    "analyst",
                    "validation.json",
                    {
                        "accepted": False,
                        "errors": ["schema_parse_failed"],
                        "schema_error": result.schema_error,
                    },
                )
                store.record_transition("ANALYST_SCHEMA_FAILED")
                summary = {"run_id": rid, "state": "ANALYST_SCHEMA_FAILED"}
                return self._finish(store, summary)
            try:
                analyst_report = AnalystReport.model_validate(result.parsed)
            except ValidationError as exc:
                if retries < self.config.ollama.max_schema_retries:
                    retries += 1
                    feedback = str(exc)
                    continue
                store.write_role_json(
                    "analyst",
                    "parsed_report.json",
                    result.parsed,
                )
                store.write_role_json(
                    "analyst",
                    "validation.json",
                    {"accepted": False, "errors": [str(exc)]},
                )
                store.record_transition("ANALYST_SCHEMA_FAILED")
                summary = {"run_id": rid, "state": "ANALYST_SCHEMA_FAILED"}
                return self._finish(store, summary)
            # Deterministic identity anchoring — models must not invent hash/id
            analyst_report = analyst_report.model_copy(
                update={
                    "diagnostic_hash": str(diagnostic.get("diagnostic_hash") or ""),
                    "diagnostic_id": a_input.diagnostic_id,
                }
            )
            store.record_transition("ANALYST_PARSED")
            store.write_role_json(
                "analyst", "parsed_report.json", analyst_report.model_dump()
            )
            a_val = validate_analyst_report(
                analyst_report, diagnostic=diagnostic, limits=self.config.limits
            )
            store.write_role_json("analyst", "validation.json", a_val.model_dump())
            if not a_val.accepted:
                # Retry only for structural evidence-path/value issues (not weak science)
                structural = [
                    e
                    for e in a_val.errors
                    if e.startswith("unresolved_evidence_path:")
                    or e.startswith("evidence_value_mismatch:")
                    or e.startswith("unsupported_metric_used:")
                ]
                if structural and retries < self.config.ollama.max_schema_retries:
                    retries += 1
                    feedback = (
                        "Evidence validation failed. Fix paths/values only; "
                        "do not invent metrics. Errors:\n"
                        + "\n".join(structural)
                    )
                    continue
                store.record_transition("ANALYST_EVIDENCE_FAILED", a_val.model_dump())
                summary = {
                    "run_id": rid,
                    "state": "ANALYST_EVIDENCE_FAILED",
                    "analyst_validation": a_val.model_dump(),
                }
                return self._finish(store, summary)
            store.record_transition("ANALYST_VALIDATED")
            break

        assert analyst_report is not None and a_val is not None and last_result is not None
        a_val_hash = validation_hash(a_val)

        # --- Scientist ---
        s_input = build_scientist_input(
            analyst_report,
            analyst_validation_hash=a_val_hash,
            dataset_contract_summary=contract_summary,
            objective_summary=objective_summary,
            required_hypotheses=self.config.limits.required_hypotheses,
        )
        store.write_role_json("scientist", "request.json", s_input.model_dump())
        store.record_transition("SCIENTIST_REQUESTED")

        retries = 0
        feedback = None
        scientist_report: ScientistReport | None = None
        s_val = None
        while True:
            result = run_scientist(
                self.backend,
                s_input,
                self.config,
                retry_feedback=feedback,
                schema_retries_so_far=retries,
            )
            store.write_role_text("scientist", "raw_response.txt", result.raw_text)
            store.write_role_json(
                "scientist", "call_record.json", result.call_record.model_dump()
            )
            if result.call_record.error_type in {
                "timeout",
                "transport_error",
                "http_error",
            }:
                store.record_transition(
                    "SCIENTIST_TRANSPORT_FAILED",
                    {"error": result.call_record.error_message},
                )
                summary = {
                    "run_id": rid,
                    "state": "SCIENTIST_TRANSPORT_FAILED",
                    "analyst_accepted": True,
                }
                return self._finish(store, summary)
            if result.parsed is None:
                if retries < self.config.ollama.max_schema_retries:
                    retries += 1
                    feedback = result.schema_error or "Invalid JSON"
                    continue
                store.record_transition("SCIENTIST_SCHEMA_FAILED")
                summary = {"run_id": rid, "state": "SCIENTIST_SCHEMA_FAILED"}
                return self._finish(store, summary)
            try:
                scientist_report = ScientistReport.model_validate(result.parsed)
            except ValidationError as exc:
                if retries < self.config.ollama.max_schema_retries:
                    retries += 1
                    feedback = str(exc)
                    continue
                store.write_role_json("scientist", "parsed_report.json", result.parsed)
                store.write_role_json(
                    "scientist",
                    "validation.json",
                    {"accepted": False, "errors": [str(exc)]},
                )
                store.record_transition("SCIENTIST_SCHEMA_FAILED")
                summary = {"run_id": rid, "state": "SCIENTIST_SCHEMA_FAILED"}
                return self._finish(store, summary)
            store.record_transition("SCIENTIST_PARSED")
            store.write_role_json(
                "scientist", "parsed_report.json", scientist_report.model_dump()
            )
            scientist_report = scientist_report.model_copy(
                update={"analyst_report_hash": hash_mapping(analyst_report.model_dump())}
            )
            ids = {
                str(p["primitive_id"])
                for p in catalogue.get("primitives", [])
                if isinstance(p, dict) and "primitive_id" in p
            }
            s_val = validate_scientist_report(
                scientist_report,
                analyst=analyst_report,
                catalogue_ids=ids,
                limits=self.config.limits,
            )
            store.write_role_json("scientist", "validation.json", s_val.model_dump())
            if not s_val.accepted:
                structural = [
                    e
                    for e in s_val.errors
                    if e.startswith(
                        (
                            "missing_invariants:",
                            "missing_falsification:",
                            "missing_evaluation_plan:",
                            "missing_primitives:",
                            "unknown_primitive:",
                            "unknown_target_mechanism:",
                            "hypothesis_count:",
                            "parameter_only_hypothesis:",
                            "hypotheses_too_similar:",
                            "hypotheses_near_duplicate:",
                        )
                    )
                ]
                if structural and retries < self.config.ollama.max_schema_retries:
                    retries += 1
                    feedback = (
                        "Hypothesis validation failed. Fix structure only. Errors:\n"
                        + "\n".join(structural)
                    )
                    continue
                store.record_transition(
                    "SCIENTIST_HYPOTHESIS_FAILED", s_val.model_dump()
                )
                summary = {
                    "run_id": rid,
                    "state": "SCIENTIST_HYPOTHESIS_FAILED",
                    "scientist_validation": s_val.model_dump(),
                }
                return self._finish(store, summary)
            store.record_transition("SCIENTIST_VALIDATED")
            break

        assert scientist_report is not None and s_val is not None
        store.record_transition("COMPLETED")
        summary = {
            "run_id": rid,
            "state": "COMPLETED",
            "label": "M6 anchored-agent integration run",
            "diagnostic_hash": diagnostic.get("diagnostic_hash"),
            "analyst_report_hash": hash_mapping(analyst_report.model_dump()),
            "analyst_validation_hash": a_val_hash,
            "scientist_report_hash": hash_mapping(scientist_report.model_dump()),
            "scientist_validation_hash": validation_hash(s_val),
            "n_mechanisms": len(analyst_report.ranked_mechanisms),
            "n_hypotheses": len(scientist_report.hypotheses),
            "hypothesis_names": [h.name for h in scientist_report.hypotheses],
            "model": getattr(self.backend, "model", self.config.ollama.model),
            "source_state": src.model_dump(),
            "ollama_calls": 2 + last_result.call_record.schema_retries,
            "solution_modified": False,
            "code_generated": False,
        }
        return self._finish(store, summary)
