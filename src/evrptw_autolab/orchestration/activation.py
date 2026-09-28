"""Architect-controlled role gating. The team always has five roles; not all run every cycle."""
from __future__ import annotations

from evrptw_autolab.agents import FIXED_ROLES, ArchitectPlan

BOOTSTRAP_ROLES = ("architect", "routing", "charging", "search", "critic")


def roles_for_phase(phase: str, plan: ArchitectPlan) -> list[str]:
    """DEBUG still calls the architect, but only Search writes solver code."""
    if phase == "DEBUG":
        return ["architect", "search", "critic"]
    return roles_for_plan(plan)


def roles_for_plan(plan: ArchitectPlan) -> list[str]:
    requested = [role for role in plan.agents_to_activate if role in FIXED_ROLES]
    if plan.target == "BOOTSTRAP":
        return list(BOOTSTRAP_ROLES)
    if plan.target == "TEST_ONLY":
        return ["architect", "critic"]
    active = ["architect"]
    for role in requested:
        if role not in active:
            active.append(role)
    if "critic" not in active:
        active.append("critic")
    return ensure_integration(active)


def ensure_integration(active: list[str]) -> list[str]:
    """Charging/routing helpers are dead unless Search rewires solve()."""
    out = list(active)
    if "routing" in out or "charging" in out:
        if "search" not in out:
            out.append("search")
    if "critic" not in out:
        out.append("critic")
    return out
