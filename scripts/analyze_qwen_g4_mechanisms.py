"""Code-level analysis of Qwen MCB V1 G4-reaching solvers (seeds 11/22/33). Analysis only."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (11, 22, 33)
PROFILE = "qwen25_coder_7b"


def _solver_path(seed: int) -> Path | None:
    candidates = [
        ROOT / "workspace" / "discovery_mcb_v1" / PROFILE / f"seed{seed}" / "committed" / "solver.py",
        ROOT / "workspace" / "discovery_mcb_v1" / PROFILE / f"seed{seed}" / "current" / "solver.py",
        ROOT
        / "results"
        / "md"
        / "artifacts"
        / "mcb_v1"
        / PROFILE
        / f"seed{seed}"
        / "solver.py",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _classify(source: str) -> dict:
    text = source
    lower = text.lower()
    routes0 = bool(re.search(r"routes\s*\[\s*0\s*\]", text))
    for_routes = bool(re.search(r"for\s+\w+\s+in\s+routes", text)) or bool(
        re.search(r"for\s+.+\s+in\s+enumerate\(\s*routes", text)
    )
    station_insert = any(
        k in lower for k in ("station", "charge", "refuel", "recharg")
    )
    propagate = "propagate_route" in text
    battery_check = "battery" in lower
    single_station = bool(re.search(r"station_ids\s*\[\s*0\s*\]", text)) or bool(
        re.search(r"list\(instance\.station_ids\)\s*\[\s*0\s*\]", text)
    )
    customer_loop = "customer_ids" in text
    # heuristic labels
    labels = []
    if routes0 and not for_routes:
        labels.append("first-route-only")
    if for_routes:
        labels.append("iterates-routes")
    if single_station:
        labels.append("single-station-only")
    if station_insert and battery_check:
        labels.append("local-negative-battery-scan")
    if customer_loop and "[[depot" in text.replace(" ", ""):
        labels.append("one-customer-per-route-skeleton")
    if not labels:
        labels.append("unclassified")
    generality = "route-specific / incomplete generalization"
    if for_routes and station_insert and not routes0:
        generality = "attempts multi-route charging (still may miss timing/energy edge cases)"
    elif routes0:
        generality = "charging/repair concentrated on routes[0]"
    return {
        "uses_propagate_route": propagate,
        "mentions_charging": station_insert,
        "battery_check": battery_check,
        "routes0_refs": len(re.findall(r"routes\s*\[\s*0\s*\]", text)),
        "iterates_routes": for_routes,
        "single_station_indexing": single_station,
        "labels": labels,
        "generality_assessment": generality,
        "n_lines": len(text.splitlines()),
        "has_solve": "def solve" in text,
    }


def main() -> None:
    blocks = []
    for seed in SEEDS:
        raw = ROOT / "results" / "md" / "tables" / "raw_autolab" / f"discovery_mcb_v1_{PROFILE}_seed{seed}.json"
        meta = json.loads(raw.read_text(encoding="utf-8")) if raw.exists() else {}
        path = _solver_path(seed)
        if path is None:
            blocks.append({"seed": seed, "error": "solver not found", "meta": {
                "G4_progress": meta.get("G4_progress"),
                "stopped": meta.get("stopped_reason"),
            }})
            continue
        source = path.read_text(encoding="utf-8")
        try:
            ast.parse(source)
            parse_ok = True
        except SyntaxError as err:
            parse_ok = False
            parse_err = str(err)
        else:
            parse_err = None
        clf = _classify(source)
        # extract a short snippet around routes[0] or charging
        snippet = ""
        for pat in (r"routes\s*\[\s*0\s*\]", r"station", r"battery", r"propagate_route"):
            m = re.search(pat, source, re.I)
            if m:
                start = max(0, source.rfind("\n", 0, m.start()) - 200)
                end = min(len(source), m.end() + 400)
                snippet = source[start:end].strip()
                break
        blocks.append(
            {
                "seed": seed,
                "path": str(path),
                "G4_progress": meta.get("G4_progress"),
                "stopped": meta.get("stopped_reason"),
                "primary": meta.get("primary_failure"),
                "parse_ok": parse_ok,
                "parse_err": parse_err,
                "classification": clf,
                "snippet": snippet[:900],
            }
        )

    lines = [
        "# Qwen G4 mechanism analysis (MCB V1 seeds 11/22/33)",
        "",
        "Analysis only — solvers are not modified.",
        "",
        "Shared pattern across G4-reaching Qwen runs:",
        "",
        "1. Build one-customer routes `[[depot, cid, depot] ...]`.",
        "2. Detect battery insufficiency (often via `propagate_route`).",
        "3. Insert a charging station — frequently applied to `routes[0]` only,",
        "   or otherwise without fully general timing/energy handling across the Schneider panel.",
        "",
        "Conceptual defect that repeats:",
        "",
        "> local mechanism discovery succeeds; systematic algorithm generalization fails.",
        "",
    ]
    for b in blocks:
        lines.append(f"## Seed {b['seed']}")
        lines.append("")
        if b.get("error"):
            lines.append(f"- **error:** {b['error']}")
            lines.append(f"- meta: `{b.get('meta')}`")
            lines.append("")
            continue
        clf = b["classification"]
        lines.extend(
            [
                f"- **path:** `{b['path']}`",
                f"- **G4_progress:** `{b['G4_progress']}` stopped=`{b['stopped']}`",
                f"- **primary:** `{b.get('primary')}`",
                f"- **labels:** {', '.join(clf['labels'])}",
                f"- **generality:** {clf['generality_assessment']}",
                f"- routes[0] refs={clf['routes0_refs']} iterate_routes={clf['iterates_routes']} "
                f"single_station_idx={clf['single_station_indexing']} "
                f"propagate={clf['uses_propagate_route']}",
                "",
                "```python",
                b.get("snippet") or "# (no snippet)",
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Conclusion",
            "",
            "For the three Qwen runs that reached the real Schneider G4 panel, charging logic is",
            "present but typically **not fully general** across all routes / families / timing",
            "conditions. Remaining failures are dominated by **BATTERY** (and historically WINDOW",
            "on r105C5 in related repair seeds). This supports the paper claim that small models",
            "can synthesize local charging repairs while failing systematic generalization.",
            "",
        ]
    )
    md = ROOT / "results" / "md" / "QWEN_G4_MECHANISM_ANALYSIS.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    (ROOT / "results" / "md" / "tables" / "raw_autolab" / "qwen_g4_mechanism_analysis.json").write_text(
        json.dumps(blocks, indent=2), encoding="utf-8"
    )
    print(f"wrote {md}")


if __name__ == "__main__":
    main()
