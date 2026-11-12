"""Deterministic capability checks. A model prediction cannot override these."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields

from evrptw_autolab.discovery.policy_language import (
    PolicyError,
    evaluate_policy,
    normalize_expression,
    validate_expression,
)
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.v2.types import CapabilityFlags


def capability_names() -> set[str]:
    return {item.name for item in fields(CapabilityFlags)}


def compatibility_failures(
    operator: OperatorSpec,
    flags: CapabilityFlags,
    *,
    available_features: set[str] | frozenset[str] | None = None,
    context: Mapping[str, float] | None = None,
) -> list[str]:
    """Return the reasons an operator must not run. An empty list means it may run.

    When ``available_features`` is provided, required features and hard-precondition
    expressions are checked against that name set. When ``context`` is provided,
    each hard precondition is evaluated and must score strictly positive.
    """
    known = capability_names()
    failures: list[str] = []
    for name in operator.required_capabilities:
        if name not in known:
            failures.append(f"unknown required capability {name}")
        elif not bool(getattr(flags, name)):
            failures.append(f"missing required capability {name}")
    for name in operator.forbidden_capabilities:
        if name not in known:
            failures.append(f"unknown forbidden capability {name}")
        elif bool(getattr(flags, name)):
            failures.append(f"forbidden capability {name} is present")
    if available_features is not None:
        for name in operator.required_features:
            if name not in available_features:
                failures.append(f"missing required feature {name}")
        for precondition in operator.hard_preconditions:
            if not precondition.strip():
                failures.append("empty hard precondition")
                continue
            try:
                validate_expression(precondition, set(available_features))
            except PolicyError as exc:
                failures.append(f"invalid hard precondition: {exc}")
    else:
        for precondition in operator.hard_preconditions:
            if not precondition.strip():
                failures.append("empty hard precondition")
    if context is not None:
        feature_names = set(context)
        for name in operator.required_features:
            if name not in feature_names:
                failures.append(f"missing required feature {name}")
        for precondition in operator.hard_preconditions:
            if not precondition.strip():
                failures.append("empty hard precondition")
                continue
            try:
                score = evaluate_policy(normalize_expression(precondition), context)
            except PolicyError as exc:
                failures.append(f"hard precondition failed: {exc}")
                continue
            if score <= 0.0:
                failures.append(f"hard precondition not satisfied: {precondition}")
    return failures
