"""Serialize OperatorSpec across the spawn boundary."""

from __future__ import annotations

from typing import Any

from evrptw_autolab.discovery.controller import operator_fingerprint
from evrptw_autolab.discovery.schemas import OperatorSpec


def encode_policy(policy: object | None) -> str | None:
    """Return OperatorSpec JSON for the child process, or None for classical search."""
    if policy is None:
        return None
    if not isinstance(policy, OperatorSpec):
        raise TypeError("spawned solvers accept OperatorSpec or None")
    operator = policy
    if not operator.source_hash:
        operator = operator.model_copy(update={"source_hash": operator_fingerprint(operator)})
    return operator.model_dump_json()


def decode_policy(payload: str | None) -> OperatorSpec | None:
    if not payload:
        return None
    return OperatorSpec.model_validate_json(payload)


def attribution_fields(policy: object | None, solution_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fields that describe what the executed search actually used."""
    meta: dict[str, Any] = dict(solution_metadata or {})
    raw_decision = meta.get("search_decision")
    decision: dict[str, Any] = raw_decision if isinstance(raw_decision, dict) else {}
    changed_decisions = int(meta.get("changed_decisions") or 0)
    if decision.get("changed"):
        changed_decisions = max(changed_decisions, 1)
    executed = isinstance(policy, OperatorSpec)
    source_hash = None
    if executed:
        raw_hash = getattr(policy, "source_hash", "") or ""
        source_hash = raw_hash or None
    return {
        "policy_executed": executed,
        "policy_applied": executed,
        "method_attribution": "llm_policy_search" if executed else "classical_baseline",
        "operator_id": getattr(policy, "operator_id", None) if executed else None,
        "operator_version": getattr(policy, "version", None) if executed else None,
        "source_hash": source_hash,
        "selected_move_changed": bool(decision.get("changed")),
        "changed_decisions": changed_decisions,
        "llm_calls": int(meta.get("llm_calls") or 0),
        "prompt_tokens": int(meta.get("prompt_tokens") or 0),
        "completion_tokens": int(meta.get("completion_tokens") or 0),
        "experiment_partition": meta.get("experiment_partition"),
    }
