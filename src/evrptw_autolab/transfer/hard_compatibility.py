"""Deterministic capability checks. A model prediction cannot override these."""

from __future__ import annotations

from dataclasses import fields

from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.v2.types import CapabilityFlags


def capability_names() -> set[str]:
    return {item.name for item in fields(CapabilityFlags)}


def compatibility_failures(operator: OperatorSpec, flags: CapabilityFlags) -> list[str]:
    """Return the reasons an operator must not run. An empty list means it may run."""
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
    return failures
