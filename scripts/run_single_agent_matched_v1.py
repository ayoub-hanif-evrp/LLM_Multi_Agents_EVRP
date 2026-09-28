"""Run SINGLE_AGENT_MATCHED_V1 for one seed (matched token budget vs Qwen MCB V1)."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evrptw_autolab.build.single_agent_matched_v1 import (  # noqa: E402
    PROTOCOL_NAME,
    run_single_agent_matched_v1,
)
from evrptw_autolab.llm.ollama import OllamaBackend  # noqa: E402
from evrptw_autolab.llm.registry import availability, resolve_profile  # noqa: E402

# Matched to actual Qwen MCB V1 seeded totals (prompt+completion).
TOKEN_BUDGETS = {
    11: 18179,
    22: 39157,
    33: 23579,
    44: 6205,
    55: 18207,
}


def _safe_run_id(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw.strip())
    if not cleaned:
        raise ValueError("empty --run-id")
    return cleaned


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="qwen25_coder_7b")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--llm-seed", type=int, required=True)
    parser.add_argument("--max-total-tokens", type=int, default=None)
    args = parser.parse_args()

    seed = int(args.llm_seed)
    budget = args.max_total_tokens if args.max_total_tokens is not None else TOKEN_BUDGETS.get(seed)
    if budget is None:
        print(f"FAILED: no token budget for seed={seed}; pass --max-total-tokens")
        sys.exit(2)
    run_id = _safe_run_id(args.run_id or f"single_qwen_seed{seed}")

    profile = resolve_profile(args.profile)
    backend = OllamaBackend(
        timeout_s=float(profile.timeout_s or 180.0),
        num_ctx=min(profile.num_ctx, 4096),
        keep_alive="10m",
        seed=seed,
    )
    if availability(profile, backend) != "installed":
        print(f"FAILED: model not installed ({args.profile})")
        sys.exit(2)

    workspace = ROOT / "workspace" / "discovery_single_agent_v1" / profile.id / run_id
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)

    print(
        f"{PROTOCOL_NAME} model={profile.model} run_id={run_id} "
        f"llm_seed={seed} max_total_tokens={budget}",
        flush=True,
    )
    report = run_single_agent_matched_v1(
        model=profile.model,
        backend=backend,
        workspace=workspace,
        max_total_tokens=budget,
        temperature=(profile.temperatures or {}).get("routing", 0.25),
    )

    gates = {
        name: {"passed": g.passed, "detail": g.detail, "agent": g.agent}
        for name, g in report.gates.items()
    }
    summary = next((x for x in report.agent_log if x.get("kind") == "campaign_summary"), {}) or {}
    tax = summary.get("taxonomy") or {}
    pf = summary.get("primary_failure")

    payload = {
        "protocol": PROTOCOL_NAME,
        "model": profile.model,
        "profile": profile.id,
        "run_id": run_id,
        "llm_seed": seed,
        "seed_provided": True,
        "max_total_tokens": budget,
        "total_tokens": report.total_tokens,
        "prompt_tokens": report.prompt_tokens,
        "completion_tokens": report.completion_tokens,
        "token_budget_exhausted": report.token_budget_exhausted,
        "llm_calls": report.llm_calls,
        "wall_s": report.wall_s,
        "gates": gates,
        "G4_progress": report.g4_progress,
        "G4_PASS": bool(gates.get("G4", {}).get("passed")),
        "highest_gate": report.highest_gate,
        "stopped_reason": report.stopped_reason,
        "primary_failure": pf,
        "taxonomy_counts": tax,
        "family_counts": report.family_counts,
        "noop_count": report.noop_count,
        "distinct_committed_hashes": report.distinct_committed_hashes,
        "final_solver_hash": report.final_solver_hash,
        "solver_path": report.solver_path,
        "all_c5_unchanged": report.c5_generalization or None,
        "agent_log": report.agent_log,
        "created_utc": datetime.now(UTC).isoformat(),
    }

    dest = ROOT / "results" / "md" / "tables" / "raw_autolab"
    dest.mkdir(parents=True, exist_ok=True)
    json_path = dest / f"discovery_single_agent_v1_{profile.id}_{run_id}.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    md = ROOT / "results" / "md" / f"SA_V1_{profile.id}_{run_id}_REPORT.md"
    lines = [
        f"# {PROTOCOL_NAME} — `{run_id}`",
        "",
        f"**Model:** `{profile.model}` | **seed:** `{seed}` | **token budget:** `{budget}`",
        "",
        f"- highest_gate: `{report.highest_gate}`",
        f"- G4: `{report.g4_progress}` stopped=`{report.stopped_reason}`",
        f"- calls={report.llm_calls} tokens={report.total_tokens} "
        f"(prompt={report.prompt_tokens} completion={report.completion_tokens})",
        f"- wall_s={report.wall_s} noop={report.noop_count} "
        f"hashes={report.distinct_committed_hashes} final_hash=`{report.final_solver_hash}`",
        f"- primary: `{pf}`",
        f"- taxonomy: `{tax}`",
        f"- families: `{report.family_counts}`",
        "",
        "## Gates",
        "",
    ]
    for name in ("G0", "G1", "G2", "G3", "G4"):
        g = gates.get(name) or {}
        lines.append(f"- **{name}**: passed={g.get('passed')} detail=`{str(g.get('detail') or '')[:160]}`")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({k: payload[k] for k in (
        "stopped_reason", "G4_progress", "G4_PASS", "highest_gate", "llm_seed",
        "llm_calls", "total_tokens", "max_total_tokens", "wall_s", "primary_failure",
    )}, indent=2))
    print(f"wrote {json_path}")
    print(f"wrote {md}")


if __name__ == "__main__":
    main()
