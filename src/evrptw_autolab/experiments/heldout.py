"""Explicit final held-out evaluation. Never used during discovery."""
from __future__ import annotations

import json
from pathlib import Path

from evrptw_autolab.evaluation.fidelity import load_all, split_instances
from evrptw_autolab.evaluation.metrics import summarize
from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.sandbox.runner import run_solver


def run_heldout(solver_dir: Path, *, log_path: Path, data_root: Path | None = None) -> dict[str, object]:
    held = split_instances(load_all(data_root))["heldout"]
    reports = [run_solver(solver_dir, instance, seed=0, limits=RunLimits()) for instance in held]
    payload = {
        "mode": "FINAL_HELDOUT",
        "family": "RC2",
        "n": len(held),
        "summary": summarize(reports),
        "instance_ids": [instance.instance_id for instance in held],
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
