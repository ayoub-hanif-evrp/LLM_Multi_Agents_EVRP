"""Link the Montoya removal ablation to its recorded source and rerun the factorial."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from evrptw_autolab.components.interfaces import DEFAULT_SOURCES, ComponentKind
from evrptw_autolab.experiments.policy_sensitivity import KINDS, ablate_components
from evrptw_autolab.problem.datasets.montoya import load_montoya

ROOT = Path(__file__).resolve().parents[3]
CAMPAIGN = ROOT / "results" / "v2" / "campaigns" / "campaign_20261017T163126Z" / "campaign.json"
INSTANCE = ROOT / "dataset" / "montoya-et-al-2017" / "tc0c10s2cf1.xml"

# The original single-agent call used this temperature. Repair, if any, uses 0.0.
# The stored status is expression_wrapped, so the first call validated.
GENERATION_TEMPERATURE = 0.2
GENERATION_ROLE = "routing"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def load_recorded_single_agent_sources(
    campaign_path: Path = CAMPAIGN,
    *,
    instance_id: str = "tc0c10s2cf1",
) -> dict[str, Any]:
    """Return the executed sources stored for one single-agent campaign row."""
    payload = json.loads(campaign_path.read_text(encoding="utf-8"))
    row = next(
        item
        for item in payload["rows"]
        if item.get("arm") == "single_agent" and item.get("instance_id") == instance_id
    )
    sources: dict[ComponentKind, str] = {}
    for item in row["attribution"]:
        kind = str(item["component"])
        if kind not in KINDS:
            continue
        sources[kind] = str(item["source"])
    missing = [kind for kind in KINDS if kind not in sources]
    if missing:
        raise ValueError(f"{campaign_path} missing sources for {missing}")
    return {"row": row, "sources": sources, "campaign": payload}


def provenance_manifest(campaign_path: Path = CAMPAIGN) -> dict[str, Any]:
    """Provenance that can be checked from committed artifacts.

    The campaign stored the executed function source. It did not store the raw
    model response or the Ollama digest, so those fields stay null.
    """
    loaded = load_recorded_single_agent_sources(campaign_path)
    sources: dict[ComponentKind, str] = loaded["sources"]
    row = loaded["row"]
    return {
        "classification": "promising_policy_ablation_incomplete_generation_provenance",
        "reason": (
            "The executed removal source is byte-linked to the single-agent row of "
            "campaign_20261017T163126Z. That full bundle was infeasible. The feasible "
            "duration gain appears only when this removal source is paired with the "
            "default insertion and station scores. The raw model response and model "
            "digest were not saved."
        ),
        "campaign_id": "campaign_20261017T163126Z",
        "campaign_path": str(campaign_path),
        "arm": "single_agent",
        "agent_role": GENERATION_ROLE,
        "agent_description": "unified single-agent designer, not the five-agent search role",
        "instance_id": row["instance_id"],
        "family": row["family"],
        "model_tag": row.get("model"),
        "model_digest": None,
        "generation_temperature": GENERATION_TEMPERATURE,
        "generation_json_mode": True,
        "original_model_response": None,
        "original_bundle_feasible": row.get("feasible"),
        "original_bundle_objective_key": row.get("objective_key"),
        "original_bundle_first_fault": row.get("first_fault"),
        "components": {
            kind: {
                "executed_source": sources[kind],
                "sha256": _sha256_text(sources[kind]),
                "is_default": sources[kind].strip() == DEFAULT_SOURCES[kind].strip(),
            }
            for kind in KINDS
        },
        "five_agent_same_instance_removal_is_different": True,
        "solver_reproduction": {
            "seed": 7,
            "time_limit_s": 10.0,
            "alns_iterations": 60,
            "hard_timeout": True,
            "note": "These are the ablation settings, not the 5-second campaign settings.",
        },
        "instance_path": str(INSTANCE),
        "instance_sha256": _sha256_file(INSTANCE) if INSTANCE.exists() else None,
        "git_head": _git_head(),
        "reproduce_command": "uv run voltforge experiments montoya-attribution",
    }


def factorial_variants(sources: dict[ComponentKind, str]) -> dict[str, dict[ComponentKind, str]]:
    """All eight subsets. Default components fill every slot that is not selected."""
    masks = [
        ("default", ()),
        ("insertion_only", ("insertion_score",)),
        ("station_only", ("station_score",)),
        ("removal_only", ("removal_priority",)),
        ("insertion_station", ("insertion_score", "station_score")),
        ("insertion_removal", ("insertion_score", "removal_priority")),
        ("station_removal", ("station_score", "removal_priority")),
        ("all_three", KINDS),
    ]
    variants: dict[str, dict[ComponentKind, str]] = {}
    for name, selected in masks:
        bundle = dict(DEFAULT_SOURCES)
        for kind in selected:
            bundle[kind] = sources[kind]
        variants[name] = bundle
    return variants


def run_factorial(
    *,
    seed: int = 7,
    time_limit_s: float = 10.0,
    alns_iterations: int = 60,
    campaign_path: Path = CAMPAIGN,
) -> dict[str, Any]:
    loaded = load_recorded_single_agent_sources(campaign_path)
    spec = load_montoya(INSTANCE)
    rows = ablate_components(
        spec,
        factorial_variants(loaded["sources"]),
        seed=seed,
        time_limit_s=time_limit_s,
        alns_iterations=alns_iterations,
        hard_timeout=True,
    )
    return {"provenance": provenance_manifest(campaign_path), "rows": rows}


DEVELOPMENT_INSTANCES: tuple[str, ...] = ("tc0c10s2cf1", "tc0c10s3cf1")
DEPLOYMENT_SEEDS: tuple[int, ...] = (7, 11, 22)


def summarize_replication(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Pair default with removal on every instance and deployment seed.

    A lower infeasible duration is not a win. One win beside a loss is a
    specialized result, not a general improvement.
    """
    grouped: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((str(row["instance_id"]), int(row["seed"])), {})[str(row["variant"])] = row
    pairs: list[dict[str, Any]] = []
    for (instance_id, seed), group in sorted(grouped.items()):
        baseline = group["default"]
        candidate = group["removal_only"]
        both_feasible = bool(baseline["feasible"]) and bool(candidate["feasible"])
        delta = None
        if both_feasible:
            delta = float(candidate["duration"]) - float(baseline["duration"])
        pairs.append(
            {
                "instance_id": instance_id,
                "seed": seed,
                "default_feasible": bool(baseline["feasible"]),
                "default_duration": baseline["duration"],
                "default_vehicles": baseline["vehicles"],
                "removal_feasible": bool(candidate["feasible"]),
                "removal_duration": candidate["duration"],
                "removal_vehicles": candidate["vehicles"],
                "paired_outcome": candidate["paired_outcome"],
                "duration_delta": delta,
                "removal_fault": candidate["first_fault"],
                "default_fault": baseline["first_fault"],
            }
        )
    wins = sum(1 for item in pairs if item["paired_outcome"] == "candidate")
    losses = sum(1 for item in pairs if item["paired_outcome"] == "baseline")
    ties = sum(1 for item in pairs if item["paired_outcome"] == "tie")
    infeasible = sum(1 for item in pairs if item["paired_outcome"] == "tie_infeasible")
    if losses or (infeasible and wins):
        classification = (
            "specialized_not_universally_superior" if wins else "no_improvement_with_regressions"
        )
    elif wins and ties:
        classification = "improves_a_subset_of_development_pairs"
    elif wins:
        classification = "improved_on_every_compared_pair"
    else:
        classification = "no_feasible_objective_gain"
    return {
        "n_pairs": len(pairs),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "tie_infeasible": infeasible,
        "classification": classification,
        "pairs": pairs,
    }


def run_removal_replication(
    *,
    instances: tuple[str, ...] = DEVELOPMENT_INSTANCES,
    seeds: tuple[int, ...] = DEPLOYMENT_SEEDS,
    time_limit_s: float = 10.0,
    alns_iterations: int = 60,
    campaign_path: Path = CAMPAIGN,
) -> dict[str, Any]:
    """Default versus the recorded removal policy on the frozen Montoya development pair."""
    loaded = load_recorded_single_agent_sources(campaign_path)
    variants = {
        name: factorial_variants(loaded["sources"])[name] for name in ("default", "removal_only")
    }
    rows: list[dict[str, Any]] = []
    for instance_id in instances:
        path = ROOT / "dataset" / "montoya-et-al-2017" / f"{instance_id}.xml"
        spec = load_montoya(path)
        digest = _sha256_file(path)
        for seed in seeds:
            for row in ablate_components(
                spec,
                variants,
                seed=seed,
                time_limit_s=time_limit_s,
                alns_iterations=alns_iterations,
                hard_timeout=True,
            ):
                row["instance_id"] = instance_id
                row["instance_sha256"] = digest
                row["alns_iterations"] = alns_iterations
                rows.append(row)
    summary = summarize_replication(rows)
    return {
        "role": "deployment_seed_replication",
        "development_instances": list(instances),
        "deployment_seeds": list(seeds),
        "time_limit_s": time_limit_s,
        "alns_iterations": alns_iterations,
        "removal_sha256": _sha256_text(loaded["sources"]["removal_priority"]),
        "historical_note": (
            "Classical durations from commit 200bb9f used the older timer and are "
            "not paired with these runs. The paired comparator is the default "
            "policy solved here under the same budget."
        ),
        "summary": summary,
        "rows": rows,
    }


def write_removal_replication(out_dir: Path | None = None) -> Path:
    out = out_dir or (ROOT / "results" / "v2" / "diagnostics" / "montoya_policy_attribution")
    out.mkdir(parents=True, exist_ok=True)
    payload = run_removal_replication()
    (out / "removal_replication.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (out / "removal_replication_summary.json").write_text(
        json.dumps(payload["summary"], indent=2),
        encoding="utf-8",
    )
    return out


def write_factorial(out_dir: Path | None = None) -> Path:
    out = out_dir or (ROOT / "results" / "v2" / "diagnostics" / "montoya_policy_attribution")
    out.mkdir(parents=True, exist_ok=True)
    payload = run_factorial()
    (out / "PROVENANCE.json").write_text(
        json.dumps(payload["provenance"], indent=2),
        encoding="utf-8",
    )
    (out / "factorial_ablation.json").write_text(
        json.dumps(payload["rows"], indent=2),
        encoding="utf-8",
    )
    summary = [
        {
            "variant": row["variant"],
            "feasible": row["feasible"],
            "objective_key": row["objective_key"],
            "vehicles": row["vehicles"],
            "duration": row["duration"],
            "paired_outcome": row["paired_outcome"],
            "route_changed": row["route_changed"],
            "first_fault": row["first_fault"],
            "scorer_calls": row["scorer_calls"],
            "completed_within_budget": row["completed_within_budget"],
        }
        for row in payload["rows"]
    ]
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return out
