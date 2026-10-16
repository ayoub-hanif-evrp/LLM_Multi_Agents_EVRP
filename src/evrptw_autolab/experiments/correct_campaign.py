"""Derive corrected tables from a historical campaign without editing raw files.

The 2026-10-16 Qwen evolution arm stored 2,621 tokens once in usage.json, then
copied that total onto five instance rows. Summing those rows produced 13,105.
This module republishes run-level usage and the frozen candidate's real
per-instance evaluations.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def correct_campaign(campaign_dir: Path, out_dir: Path | None = None) -> dict[str, Any]:
    root = Path(campaign_dir)
    dest = out_dir or (root / "corrected")
    dest.mkdir(parents=True, exist_ok=True)
    usage_path = root / "evolution" / "usage.json"
    archive_path = root / "evolution" / "archive.json"
    meta_path = root / "evolution" / "frozen_meta.json"
    usage = json.loads(usage_path.read_text(encoding="utf-8"))
    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    winner_id = str(meta.get("candidate_id") or "")
    member = next((m for m in archive.get("members") or [] if m.get("candidate_id") == winner_id), None)
    if member is None and archive.get("members"):
        member = archive["members"][0]
    genuine = int((member or {}).get("genuine_llm_components") or meta.get("genuine_llm_components") or 0)
    attribution = str((member or {}).get("attribution_category") or meta.get("attribution_category") or "")
    winner_status = "NO_LLM_WINNER" if genuine <= 0 or attribution == "pure_classical" else "LLM_CANDIDATE"
    per_instance = ((member or {}).get("panel") or {}).get("per_instance") or []
    tokens = int(usage.get("total_tokens") or 0)
    calls = int(usage.get("logical_calls") or 0)
    run = {
        "experiment_id": root.name,
        "method": "five_agent_evolution",
        "model": meta.get("model"),
        "seed": (per_instance[0].get("seed") if per_instance else None),
        "llm_calls": calls,
        "llm_tokens": tokens,
        "http_attempts": int(usage.get("http_attempts") or 0),
        "development_wall_s": usage.get("wall_s"),
        "candidate_id": winner_id,
        "attribution_category": attribution,
        "winner_status": winner_status,
        "usage_scope": "run",
        "note": "Run-level tokens. Do not multiply by instance count.",
    }
    instance_rows = []
    for row in per_instance:
        instance_rows.append(
            {
                "experiment_id": root.name,
                "method": "five_agent_evolution",
                "candidate_id": winner_id,
                "winner_status": winner_status,
                "family": row.get("family"),
                "instance_id": row.get("instance_id"),
                "seed": row.get("seed"),
                "status": "EVALUATED",
                "feasible": row.get("feasible"),
                "objective_key": row.get("objective_key"),
                "vehicles": row.get("vehicles"),
                "distance": row.get("distance"),
                "runtime_s": row.get("runtime_s"),
                "fault_family": row.get("fault_family"),
                "source_hashes": meta.get("source_hashes"),
            }
        )
    (dest / "runs.jsonl").write_text(json.dumps(run) + "\n", encoding="utf-8")
    with (dest / "instance_results.jsonl").open("w", encoding="utf-8") as handle:
        for row in instance_rows:
            handle.write(json.dumps(row) + "\n")
    summary = {
        "source": str(root),
        "raw_files_modified": False,
        "evolution_llm_tokens": tokens,
        "incorrect_sum_if_repeated_per_instance": tokens * max(len(instance_rows), 1),
        "winner_status": winner_status,
        "instances": len(instance_rows),
    }
    (dest / "CORRECTION.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
