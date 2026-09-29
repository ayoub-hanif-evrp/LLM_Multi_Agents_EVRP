"""Parallel patch proposals from five solver evolution roles."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from evrptw_autolab.agents.base import Agent, extract_json
from evrptw_autolab.evolution.patch_apply import parse_proposal_json
from evrptw_autolab.evolution.types import (
    FOCUS_CYCLE,
    ROLES,
    UNLOCK,
    Focus,
    PatchProposal,
    RoleName,
)
from evrptw_autolab.llm.usage import UsageLog
from evrptw_autolab.synthesis.contract import API_SNIPPET

ROOT = Path(__file__).resolve().parents[3]


class _PatchSchema(BaseModel):
    hypothesis: str = ""
    ops: list[dict[str, Any]] = Field(default_factory=list)


class PatchAgent(Agent[_PatchSchema]):
    role = "patcher"
    prompt_name = "evolution_patcher.md"
    schema = _PatchSchema

    def __init__(self, *args: Any, role_name: str = "patcher", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.role = role_name


ROLE_PERSPECTIVES: dict[RoleName, str] = {
    "architect": "Focus on structural solver changes (helpers, control flow) that could reduce fleet size.",
    "routing": "Focus on customer assignment / sequencing code that could serve more customers per route.",
    "charging": "Focus on energy-aware improvements that keep routes feasible after packing customers.",
    "search": "Focus on global search/control mechanisms around the current construction.",
    "critic_inventor": "Invent an alternative mechanism from the executed feasibility and fleet evidence.",
}


def focus_for_generation(generation: int) -> Focus:
    return FOCUS_CYCLE[generation % len(FOCUS_CYCLE)]


def build_patch_agents(
    backend: Any,
    *,
    model: str,
    usage_log: UsageLog | None = None,
    temperature: float = 0.35,
) -> dict[str, PatchAgent]:
    agents: dict[str, PatchAgent] = {}
    for role in ROLES:
        agents[role] = PatchAgent(
            backend,
            model=model,
            temperature=temperature,
            usage_log=usage_log,
            role_name=role,
        )
    return agents


def _metrics_brief(metrics: dict[str, Any] | None) -> dict[str, Any]:
    if not metrics:
        return {}
    return {
        "feasible": metrics.get("feasible"),
        "total": metrics.get("total"),
        "vehicles_sum": metrics.get("vehicles_sum"),
        "distance_sum": metrics.get("distance_sum"),
        "by_instance": {
            k: {"ok": v.get("ok"), "vehicles": v.get("vehicles")}
            for k, v in (metrics.get("by_instance") or {}).items()
        },
    }


def propose_one(
    agent: PatchAgent,
    *,
    role: str,
    focus: Focus,
    current_source: str,
    parent_metrics: dict[str, Any] | None,
    seed: int,
    backend: Any,
) -> PatchProposal | None:
    if hasattr(backend, "seed"):
        backend.seed = seed
    perspective = ""
    for key, value in ROLE_PERSPECTIVES.items():
        if key == role:
            perspective = value
            break
    payload = {
        "role": role,
        "generation_focus": focus,
        "unlock": UNLOCK,
        "perspective": perspective,
        "api_reference": API_SNIPPET,
        "parent_metrics": _metrics_brief(parent_metrics),
        "current_solver_py": current_source,
        "instruction": (
            f"Generation focus={focus}. Role={role}. {perspective}\n"
            f"{UNLOCK}\n"
            "Return JSON patch ops only. Prefer small ADD/REPLACE changes."
        ),
    }
    prompt = agent.prompt + "\n\nINPUT:\n" + json.dumps(payload, default=str)
    try:
        raw = agent._complete(prompt, json_mode=True)
        data = extract_json(raw)
        prop = parse_proposal_json(data, role=role, seed=seed)
        prop.raw = raw if isinstance(raw, str) else str(raw)
        return prop
    except Exception as err:  # noqa: BLE001 — candidate failures are expected
        return PatchProposal(
            hypothesis=f"propose_failed:{err}"[:200],
            ops=[],
            role=role,
            seed=seed,
            raw=str(err)[:400],
        )


def proposal_seed(seed_base: int, generation: int, role_ix: int, k: int) -> int:
    """Deterministic Ollama seed for a proposal slot."""
    return int(seed_base) * 10000 + generation * 100 + role_ix * 10 + k


def propose_generation(
    agents: dict[str, PatchAgent],
    *,
    backend: Any,
    focus: Focus,
    current_source: str,
    parent_metrics: dict[str, Any] | None,
    generation: int,
    candidates_per_role: int = 2,
    seed_base: int = 0,
) -> list[PatchProposal]:
    out: list[PatchProposal] = []
    for role_ix, role in enumerate(ROLES):
        for k in range(candidates_per_role):
            seed = proposal_seed(seed_base, generation, role_ix, k)
            prop = propose_one(
                agents[role],
                role=role,
                focus=focus,
                current_source=current_source,
                parent_metrics=parent_metrics,
                seed=seed,
                backend=backend,
            )
            if prop is not None:
                out.append(prop)
    return out


def propose_charging_repair(
    agent: PatchAgent,
    *,
    backend: Any,
    current_source: str,
    fault_detail: str,
    seed: int,
) -> PatchProposal | None:
    if hasattr(backend, "seed"):
        backend.seed = seed
    payload = {
        "role": "charging",
        "repair": True,
        "fault": fault_detail,
        "unlock": "Repair feasibility only. Preserve any vehicle-count gains if possible.",
        "api_reference": API_SNIPPET,
        "current_solver_py": current_source,
        "instruction": (
            "EXPERIMENTAL repair: the previous patch reduced vehicles but broke "
            f"energy/time feasibility ({fault_detail}). "
            "Propose ONE small charging-related ADD/REPLACE patch. JSON ops only."
        ),
    }
    prompt = agent.prompt + "\n\nINPUT:\n" + json.dumps(payload, default=str)
    try:
        raw = agent._complete(prompt, json_mode=True)
        data = extract_json(raw)
        prop = parse_proposal_json(data, role="charging", seed=seed)
        prop.raw = raw if isinstance(raw, str) else str(raw)
        return prop
    except Exception as err:  # noqa: BLE001
        return PatchProposal(
            hypothesis=f"repair_failed:{err}"[:200],
            ops=[],
            role="charging",
            seed=seed,
            raw=str(err)[:400],
        )
