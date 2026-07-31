"""Equal-budget baselines for M9B evolution comparisons."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from evocharge.evolution.gates import run_gates
from evocharge.evolution.offspring import make_offspring, seed_sources
from evocharge.reproducibility import sha256_text


def run_baselines(
    *,
    project_root: Path,
    experiment_id: str,
    budget: int = 8,
    seed: int = 2027,
) -> dict[str, Any]:
    """Compare systems under equal candidate-evaluation budgets."""
    rng = random.Random(seed)
    out_dir = project_root / "artifacts" / "evolution" / experiment_id / "baselines"
    out_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {}

    # 1) Initial unevolved H1/H2/H3
    seeds = seed_sources()
    init_rows = []
    for key in ("seed_h1", "seed_h2", "seed_h3"):
        src, _mode, _hyps = seeds[key]
        cid = f"{experiment_id}_base_init_{key}"
        gate = run_gates(src, project_root=project_root, candidate_id=cid, fidelity="short")
        init_rows.append(
            {
                "candidate_id": cid,
                "accepted": gate.get("accepted"),
                "effective_rate": (gate.get("evaluation") or {}).get(
                    "effective_behavioral_change_rate"
                ),
                "n_changed": (gate.get("evaluation") or {}).get("n_changed_instances"),
            }
        )
    results["initial_h1_h2_h3"] = init_rows

    # 2) Random valid compositions
    rand_rows = []
    for i in range(budget):
        src, plan, suffix = make_offspring(
            mode="random_composition", rng=rng, parent_ids=[], generation=0
        )
        cid = f"{experiment_id}_base_randcomp_{suffix}_{i}"
        gate = run_gates(src, project_root=project_root, candidate_id=cid, fidelity="short")
        rand_rows.append(
            {
                "candidate_id": cid,
                "accepted": gate.get("accepted"),
                "source_hash": sha256_text(src),
                "plan": plan.model_dump(),
                "effective_rate": (gate.get("evaluation") or {}).get(
                    "effective_behavioral_change_rate"
                ),
            }
        )
    results["random_composition"] = rand_rows

    # 3) Random mutation (non-LLM)
    mut_rows = []
    for i in range(budget):
        src, plan, suffix = make_offspring(
            mode="baseline_random_mutation",
            rng=rng,
            parent_ids=["seed_h2"],
            generation=0,
        )
        cid = f"{experiment_id}_base_randmut_{suffix}_{i}"
        gate = run_gates(src, project_root=project_root, candidate_id=cid, fidelity="short")
        mut_rows.append(
            {
                "candidate_id": cid,
                "accepted": gate.get("accepted"),
                "effective_rate": (gate.get("evaluation") or {}).get(
                    "effective_behavioral_change_rate"
                ),
            }
        )
    results["random_mutation"] = mut_rows

    # 4) Non-LLM structured evolution sample
    nonllm_rows = []
    for i in range(budget):
        src, plan, suffix = make_offspring(
            mode="baseline_non_llm",
            rng=rng,
            parent_ids=["seed_h2", "seed_h3"],
            generation=0,
        )
        cid = f"{experiment_id}_base_nonllm_{suffix}_{i}"
        gate = run_gates(src, project_root=project_root, candidate_id=cid, fidelity="short")
        nonllm_rows.append(
            {
                "candidate_id": cid,
                "accepted": gate.get("accepted"),
                "effective_rate": (gate.get("evaluation") or {}).get(
                    "effective_behavioral_change_rate"
                ),
            }
        )
    results["non_llm_structured"] = nonllm_rows

    # 5) No-op control
    src, _mode, _hyps = seeds["seed_noop"]
    cid = f"{experiment_id}_base_noop"
    gate = run_gates(src, project_root=project_root, candidate_id=cid, fidelity="short")
    results["noop_control"] = {
        "candidate_id": cid,
        "accepted": gate.get("accepted"),
        "effective_rate": (gate.get("evaluation") or {}).get(
            "effective_behavioral_change_rate"
        ),
        "note": "Must not be scored as useful solely for feasibility preservation.",
    }

    # 6) Handcrafted analogue wrapper
    src, _mode, _hyps = seeds["seed_analogue"]
    cid = f"{experiment_id}_base_analogue"
    gate = run_gates(src, project_root=project_root, candidate_id=cid, fidelity="short")
    results["handcrafted_analogue"] = {
        "candidate_id": cid,
        "accepted": gate.get("accepted"),
        "effective_rate": (gate.get("evaluation") or {}).get(
            "effective_behavioral_change_rate"
        ),
    }

    results["budget_per_arm"] = budget
    results["equal_budget"] = True
    results["llm_without_feedback_note"] = (
        "LLM-without-numerical-feedback arm deferred to stronger-model replication; "
        "structured modification plans used for controlled M9B on qwen3:4b workstation."
    )
    (out_dir / "baselines_summary.json").write_text(
        __import__("json").dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return results
