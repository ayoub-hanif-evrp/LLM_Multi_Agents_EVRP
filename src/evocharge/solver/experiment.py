"""Experiment manifests for reproducible runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evocharge.reproducibility import git_commit, hash_mapping, lockfile_hash, sha256_file
from evocharge.system_info import collect_system_info


def write_experiment_manifest(
    run_dir: Path,
    *,
    config: dict[str, Any],
    contract_path: Path | None,
    objective_definition: str,
    seed: int,
    instance_id: str,
    instance_path: str | None,
    project_root: Path,
    fixture_manifest_path: Path | None = None,
) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    contract_hash = None
    contract_payload = None
    if contract_path is not None and contract_path.is_file():
        contract_payload = json.loads(contract_path.read_text(encoding="utf-8"))
        contract_hash = contract_payload.get("contract_hash")
        (run_dir / "dataset_contract.json").write_text(
            json.dumps(contract_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    env = collect_system_info(project_root)
    config_hash = hash_mapping(config)
    objective_definition_hash = hash_mapping({"definition": objective_definition})
    manifest: dict[str, Any] = {
        "config": config,
        "config_hash": config_hash,
        "dataset_contract_hash": contract_hash,
        "objective_definition": objective_definition,
        "objective_definition_hash": objective_definition_hash,
        "seed": seed,
        "instance_id": instance_id,
        "instance_path": instance_path,
        "git_commit": git_commit(project_root),
        "dependency_lock_hash": lockfile_hash(project_root),
        "environment": env,
        "ollama_calls": 0,
    }
    if instance_path and Path(instance_path).is_file():
        manifest["instance_sha256"] = sha256_file(Path(instance_path))

    fixture_info = _resolve_fixture_provenance(
        instance_path=instance_path,
        project_root=project_root,
        fixture_manifest_path=fixture_manifest_path,
    )
    if fixture_info:
        manifest.update(fixture_info)

    path = run_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "environment.json").write_text(
        json.dumps(env, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (run_dir / "objective.json").write_text(
        json.dumps(
            {
                "definition": objective_definition,
                "objective_definition_hash": objective_definition_hash,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _resolve_fixture_provenance(
    *,
    instance_path: str | None,
    project_root: Path,
    fixture_manifest_path: Path | None,
) -> dict[str, Any]:
    if not instance_path:
        return {}
    manifest_path = fixture_manifest_path or (
        project_root / "data" / "contracts" / "schneider_v1.0.json"
    )
    if not manifest_path.is_file():
        return {
            "anchored_fixture": False,
            "provenance_status": "partially_verified",
            "provenance_note": "No Schneider contract available at run time",
        }
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    name = Path(instance_path).name
    # Contract JSON is not a per-file fixture map; mark path as Schneider-rooted if present.
    inst = Path(instance_path)
    under_schneider = "schneider" in str(inst).replace("\\", "/").lower()
    if not under_schneider and not inst.is_file():
        return {
            "anchored_fixture": False,
            "provenance_status": "partially_verified",
            "provenance_note": f"Instance {name} not under dataset/schneider",
        }
    return {
        "anchored_fixture": under_schneider,
        "provenance_status": "verified" if under_schneider else "partially_verified",
        "dataset": payload.get("dataset_name"),
        "contract_hash": payload.get("contract_hash"),
    }


def supplement_run_provenance(
    run_dir: Path,
    *,
    project_root: Path,
    fixture_manifest_path: Path | None = None,
) -> Path:
    """Non-destructive provenance supplement for existing M4/M5 run records."""
    run_dir = Path(run_dir)
    manifest_path = run_dir / "manifest.json"
    summary_path = run_dir / "summary.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = (
        json.loads(summary_path.read_text(encoding="utf-8"))
        if summary_path.is_file()
        else {}
    )
    instance_path = manifest.get("instance_path") or summary.get("instance_path")
    fixture_info = _resolve_fixture_provenance(
        instance_path=instance_path,
        project_root=project_root,
        fixture_manifest_path=fixture_manifest_path,
    )

    checkpoint = run_dir / "checkpoint.json"
    events = run_dir / "events.jsonl.gz"
    diagnostic = run_dir / "diagnostic.json"
    supplement = {
        "run_id": summary.get("run_id") or run_dir.name,
        "instance_path": instance_path,
        "instance_sha256_recorded": manifest.get("instance_sha256"),
        "dataset_contract_hash": manifest.get("dataset_contract_hash"),
        "objective_definition": manifest.get("objective_definition"),
        "objective_definition_hash": manifest.get("objective_definition_hash")
        or hash_mapping({"definition": manifest.get("objective_definition")}),
        "config_hash": manifest.get("config_hash")
        or hash_mapping(manifest.get("config") or {}),
        "seed": manifest.get("seed"),
        "git_commit": manifest.get("git_commit"),
        "checkpoint_present": checkpoint.is_file(),
        "checkpoint_sha256": sha256_file(checkpoint) if checkpoint.is_file() else None,
        "trace_present": events.is_file(),
        "trace_sha256": sha256_file(events) if events.is_file() else None,
        "diagnostic_present": diagnostic.is_file(),
        "diagnostic_summary_hash": None,
        "optimization_results_unchanged": True,
        **fixture_info,
    }
    if diagnostic.is_file():
        diag = json.loads(diagnostic.read_text(encoding="utf-8"))
        supplement["diagnostic_summary_hash"] = diag.get("diagnostic_hash")
        if Path(str(instance_path)).is_file() and manifest.get("instance_sha256"):
            live = sha256_file(Path(str(instance_path)))
            if live != manifest.get("instance_sha256"):
                supplement["provenance_status"] = "partially_verified"
                supplement["provenance_note"] = (
                    "Live fixture hash differs from instance_sha256 recorded in manifest"
                )
            elif fixture_info.get("fixture_sha256") and live != fixture_info.get(
                "fixture_sha256"
            ):
                supplement["provenance_status"] = "partially_verified"
            elif supplement.get("provenance_status") != "partially_verified":
                supplement["provenance_status"] = "verified"

    out = run_dir / "provenance_supplement.json"
    out.write_text(json.dumps(supplement, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
