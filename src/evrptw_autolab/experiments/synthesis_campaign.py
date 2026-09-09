"""Evolution campaign over a homogeneous five-agent team."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from evrptw_autolab.evaluation.fidelity import by_customer_count, load_all, split_instances
from evrptw_autolab.evaluation.runner import evaluate_fidelity
from evrptw_autolab.orchestration.cycle import run_cycle
from evrptw_autolab.orchestration.handshake import pick_cycle_instance
from evrptw_autolab.orchestration.state import CampaignState
from evrptw_autolab.problem.private import smoke_instance
from evrptw_autolab.sandbox.limits import limits_from_synthesis
from evrptw_autolab.synthesis.bootstrap import bootstrap_solver


def _acceptance_panel(discovery_small: list) -> list:
    """Fixed small panel for elite selection: diagnose locally, select globally."""
    wanted = ("c101C5", "c103C5", "r104C5", "r105C5")
    by_id = {i.instance_id: i for i in discovery_small}
    panel = [by_id[name] for name in wanted if name in by_id]
    if len(panel) < 2:
        return list(discovery_small[:4])
    return panel


def run_campaign(
    *,
    model: str,
    backend: Any,
    workspace: Path,
    cycles: int,
    campaign_id: str = "campaign",
    model_id: str = "",
    temperatures: dict[str, float] | None = None,
    data_root: Path | None = None,
) -> CampaignState:
    if cycles < 1:
        raise ValueError("cycles must be >= 1")
    state_path = workspace / "campaigns" / f"{campaign_id}.json"
    discovery = split_instances(load_all(data_root))["discovery"]
    smoke = by_customer_count(discovery, [5])
    if not smoke:
        raise RuntimeError("no 5-customer discovery instances")
    panel = _acceptance_panel(smoke)
    existing = workspace / "candidates" / "S000"
    if state_path.exists():
        state = CampaignState.load(state_path)
    elif existing.exists() and any(existing.rglob("*.py")):
        state = CampaignState(
            campaign_id=campaign_id,
            model=model,
            model_id=model_id,
            team_mode="five_agent",
            cycle=0,
            elite_id="S000",
            activated_history=[{"cycle": 0, "activated": [], "why": "RESUME_S000"}],
        )
        state.save(state_path)
    else:
        boot = bootstrap_solver(
            workspace,
            backend,
            model=model,
            instance=smoke_instance(1),
            temperatures=temperatures,
            discovery=discovery,
        )
        state = CampaignState(
            campaign_id=campaign_id,
            model=model,
            model_id=model_id,
            team_mode="five_agent",
            cycle=0,
            elite_id=str(boot["solver_id"]),
            activated_history=[{"cycle": 0, "activated": boot["activated"], "why": "BOOTSTRAP"}],
        )
        state.save(state_path)
    while state.cycle < cycles:
        if state.elite_id is None:
            raise RuntimeError("campaign has no elite")
        print(f"cycle {state.cycle + 1}/{cycles} elite={state.elite_id}", flush=True)
        parent_dir = workspace / "candidates" / str(state.elite_id)
        cycle_instance, _ = pick_cycle_instance(
            parent_dir, smoke, limits=limits_from_synthesis()
        )
        print(f"  instance={cycle_instance.instance_id}", flush=True)
        try:
            result = run_cycle(
                workspace,
                backend,
                model=model,
                parent_id=state.elite_id,
                instance=cycle_instance,
                temperatures=temperatures,
                acceptance_panel=panel,
            )
        except Exception as error:  # noqa: BLE001 — keep equal-budget cycles going
            state.cycle += 1
            state.activated_history.append(
                {"cycle": state.cycle, "activated": [], "why": "CYCLE_FAILED", "error": str(error)[-800:]}
            )
            state.save(state_path)
            print(f"cycle {state.cycle} failed: {error}", flush=True)
            continue
        state.cycle += 1
        state.elite_id = str(result["elite_id"])
        state.activated_history.append(
            {"cycle": state.cycle, "activated": result["activated"], "why": result["why"]}
        )
        state.save(state_path)
    elite_dir = workspace / "candidates" / str(state.elite_id)
    if elite_dir.exists():
        f1 = evaluate_fidelity(
            elite_dir, discovery, "F1", seeds=[0], limits=limits_from_synthesis(), max_instances=8
        )
        state.activated_history.append({"cycle": state.cycle, "f1": f1, "why": "F1_ELITE"})
        state.save(state_path)
    return state
