"""Summarize MCB V1 cross-model screening table (post-hoc; no protocol changes)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "md" / "tables" / "raw_autolab"

# Screening set: one accepted measurement per model under frozen MCB V1.
RUNS = [
    ("deepseek_coder_67b", "synth04", "deepseek-coder:6.7b"),
    ("qwen25_coder_7b", "screen01", "qwen2.5-coder:7b"),
    ("codellama_7b", "screen01", "codellama:7b"),
]


def _row(path: Path, label: str) -> dict | None:
    if not path.exists():
        return None
    j = json.loads(path.read_text(encoding="utf-8"))
    gates = j.get("gates") or {}

    def g(name: str) -> str:
        if name not in gates:
            return "—"
        return "✓" if gates[name].get("passed") else "✗"

    highest = "none"
    for name, title in (
        ("G4", "G4 panel"),
        ("G3", "two-customer feasible"),
        ("G2", "charging-required"),
        ("G1", "basic feasible routing"),
        ("G0", "executable"),
    ):
        if gates.get(name, {}).get("passed"):
            highest = title
            break
    # If G0/G1 pass but G2 fail, highest is basic routing
    if gates.get("G1", {}).get("passed") and not gates.get("G2", {}).get("passed"):
        highest = "basic feasible routing"
    elif gates.get("G0", {}).get("passed") and not gates.get("G1", {}).get("passed"):
        highest = "executable"
    pf = j.get("primary_failure") or {}
    return {
        "model": label,
        "run_id": j.get("run_id"),
        "G0": g("G0"),
        "G1": g("G1"),
        "G2": g("G2"),
        "G3": g("G3"),
        "G4": g("G4"),
        "highest": highest,
        "stopped": j.get("stopped_reason"),
        "calls": j.get("llm_calls"),
        "roles": j.get("roles_invoked") or [],
        "team_incomplete": j.get("team_incomplete_orchestration"),
        "primary": pf,
        "taxonomy": j.get("taxonomy_counts") or {},
        "mechanism_diversity": j.get("mechanism_diversity") or {},
        "G4_PASS": j.get("G4_PASS"),
    }


def main() -> None:
    rows = []
    for pid, run_id, label in RUNS:
        path = RAW / f"discovery_mcb_v1_{pid}_{run_id}.json"
        # DeepSeek synth04 already written by V1 runner
        r = _row(path, label)
        if r is None:
            rows.append({"model": label, "run_id": run_id, "status": "PENDING"})
        else:
            rows.append(r)

    out = {
        "protocol": "MINIMAL_COOPERATIVE_BUILD_V1",
        "experiment": "cross_model_empty_workspace_screening",
        "rows": rows,
    }
    dest = RAW / "mcb_v1_screening_summary.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")

    lines = [
        "# MCB V1 — Cross-model empty-workspace screening",
        "",
        "Protocol **frozen**. Same MCB V1 for every model. Optimization locked.",
        "",
        "| Model | G0 | G1 | G2 | G3 | G4 | Highest capability | Stopped | Calls | Roles | Primary failure |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for r in rows:
        if r.get("status") == "PENDING":
            lines.append(
                f"| `{r['model']}` | ? | ? | ? | ? | ? | pending `{r['run_id']}` | — | — | — | — |"
            )
            continue
        pf = r.get("primary") or {}
        pf_s = (
            f"{pf.get('failure_class')}/{pf.get('detail')}"
            if pf
            else "—"
        )
        lines.append(
            f"| `{r['model']}` | {r['G0']} | {r['G1']} | {r['G2']} | {r['G3']} | {r['G4']} | "
            f"{r['highest']} | {r['stopped']} | {r['calls']} | "
            f"{','.join(r['roles'])} | {pf_s} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- DeepSeek `synth04` is the first accepted clean measurement (G2 BATTERY).",
            "- Screening uses `run_id=screen01` for other models; do not cherry-pick reruns.",
            "- Stronger anchors (DeepSeek-Coder-V2-Lite / Qwen3-Coder) require install + registry entry later.",
            "",
            "## Contrast with Phase A repair",
            "",
            "| Experiment | DeepSeek outcome |",
            "| --- | --- |",
            "| P1.3 repair of Qwen 3/4 seed | 4/4 → 12/12 C5 |",
            "| MCB V1 empty-workspace synthesis | G0✓ G1✓ G2 BATTERY ✗ |",
            "",
        ]
    )
    md = ROOT / "results" / "md" / "MCB_V1_SCREENING.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(rows, indent=2))
    print(f"wrote {md}")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
