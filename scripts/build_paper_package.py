"""Regenerate the paper tables from raw result files.

Numbers are copied from those files. This script does not solve instances.
"""
from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "results" / "v2" / "paper"
DUPLICATE = "tc0c10s3cf1"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _git() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _key(value: Any) -> str:
    if value is None:
        return ""
    return json.dumps(value)


def _freeze_rows() -> list[dict[str, Any]]:
    panel = _load(ROOT / "results" / "v2" / "manifests" / "development_panel.json")
    limits = {(row["family"], row["instance_id"]): float(row["time_limit_s"]) for row in panel["instances"]}
    rows = []
    freeze = ROOT / "results" / "v2" / "baselines" / "classical_frozen_c2de5a0"
    for path in sorted(freeze.glob("run_*/pilot.json")):
        payload = _load(path)
        for row in payload["rows"]:
            limit = limits[(row["family"], row["instance_id"])]
            runtime = float(row["runtime_s"])
            rows.append(
                {
                    "family": row["family"],
                    "instance_id": row["instance_id"],
                    "seed": int(row["seed"]),
                    "feasible": bool(row["feasible"]),
                    "objective_key": _key(row["objective_key"]),
                    "vehicles": row["vehicles"],
                    "distance": row["distance"],
                    "runtime_s": round(runtime, 6),
                    "time_limit_s": limit,
                    "within_parent_budget": runtime <= limit + 0.05,
                    "independent": row["instance_id"] != DUPLICATE,
                    "source": str(path.relative_to(ROOT)),
                }
            )
    return rows


def _feasibility(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not row["independent"]:
            continue
        grouped.setdefault(str(row["family"]), []).append(row)
    out = []
    for family in sorted(grouped):
        items = grouped[family]
        out.append(
            {
                "study": "classical_frozen_c2de5a0",
                "family": family,
                "independent_rows": len(items),
                "feasible": sum(1 for row in items if row["feasible"]),
                "within_parent_budget": sum(1 for row in items if row["within_parent_budget"]),
            }
        )
    return out


def _generational() -> dict[str, Any] | None:
    studies = _studies()
    for study in studies:
        if study["_study"] == "specialist_schedule_seed7":
            return study
    return studies[-1] if studies else None


def _studies() -> list[dict[str, Any]]:
    named = [
        (
            "results/v2/campaigns/generational_qwen_20261019T182727Z/generational.json",
            "specialist_schedule_seed7",
            "Rotating specialist prompts. The five-agent arm adds a critic and does not call an architect",
        ),
        (
            "results/v2/campaigns/generational_qwen_20261019T183813Z/generational.json",
            "specialist_schedule_seed13",
            "Independent discovery seed using the same specialist-role schedule as 182727Z",
        ),
    ]
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relative, study, design in named:
        path = ROOT / relative
        if not path.exists():
            continue
        payload = _load(path)
        payload["_path"] = relative.replace("\\", "/")
        payload["_study"] = study
        payload["_design"] = design
        found.append(payload)
        seen.add(payload["_path"])
    for path in sorted((ROOT / "results" / "v2" / "campaigns").glob("generational_qwen_*/generational.json")):
        relative = str(path.relative_to(ROOT)).replace("\\", "/")
        if relative in seen:
            continue
        payload = _load(path)
        if payload.get("workflow") != "unified_versus_architect_specialist_critic":
            continue
        payload["_path"] = relative
        payload["_study"] = f"role_split_seed{payload.get('seed')}"
        payload["_design"] = str(payload["workflow"])
        found.append(payload)
    return found


def _comparison_rows(gen: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in gen["classical"]:
        rows.append(
            {
                "study": gen.get("_study", "generational_qwen_seed7"),
                "arm": "classical",
                "candidate_id": "default",
                "generation": "",
                "instance_id": row["instance_id"],
                "seed": row["seed"],
                "feasible": row["feasible"],
                "objective_key": _key(row["objective_key"]),
                "accepted": "",
                "wins": "",
                "losses": "",
                "reason": "",
            }
        )
    for arm in ("random_evolution", "single_agent", "five_agent"):
        for item in gen[arm]:
            for row in item["rows"]:
                decision = item["decision"]
                rows.append(
                    {
                        "study": gen.get("_study", "generational_qwen_seed7"),
                        "arm": arm,
                        "candidate_id": item["candidate_id"],
                        "generation": item["generation"],
                        "instance_id": row["instance_id"],
                        "seed": row["seed"],
                        "feasible": row["feasible"],
                        "objective_key": _key(row["objective_key"] if row["feasible"] else None),
                        "accepted": item["accepted"],
                        "wins": decision.get("wins"),
                        "losses": decision.get("losses"),
                        "reason": decision.get("reason"),
                    }
                )
    return rows


def _evolution_rows(gen: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for arm in ("random_evolution", "single_agent", "five_agent"):
        for item in gen[arm]:
            decision = item["decision"]
            rows.append(
                {
                    "study": gen.get("_study", "generational"),
                    "arm": arm,
                    "generation": item["generation"],
                    "oneshot": item["oneshot"],
                    "candidate_id": item["candidate_id"],
                    "parent_id": item["parent_id"],
                    "accepted": item["accepted"],
                    "behavior_changed": item["behavior_changed"],
                    "reason": decision.get("reason"),
                    "wins": decision.get("wins"),
                    "losses": decision.get("losses"),
                    "ties": decision.get("ties"),
                    "origin": item["origin"],
                }
            )
    return rows


def _historical_ablations() -> list[dict[str, Any]]:
    specs = [
        ("primary", "matched_qwen_20261018T205937Z"),
        ("no_critic", "matched_qwen_no_critic_20261018T234819Z"),
        ("no_evolution", "matched_qwen_no_evolution_20261018T235444Z"),
        ("no_selection", "matched_qwen_no_selection_20261018T235642Z"),
    ]
    rows = []
    for name, folder in specs:
        payload = _load(ROOT / "results" / "v2" / "campaigns" / folder / "matched_pilot.json")
        selected = payload.get("selections", {}).get("five_agent", {})
        rows.append(
            {
                "study": "matched_qwen_20261018",
                "ablation": name,
                "solver_commit": payload.get("git_commit"),
                "five_agent_solves": payload.get("solver_solves", {}).get("five_agent"),
                "five_agent_calls": payload.get("llm_calls", {}).get("five_agent"),
                "five_agent_tokens": payload.get("llm_tokens", {}).get("five_agent"),
                "five_agent_selected": selected.get("selected_candidate_id"),
                "note": "fresh sample on the old solver; not a replay of the 2026-10-19 generational run",
            }
        )
    return rows


def _compute(gen: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    if gen is not None:
        for arm, solves in gen["solver_solves"].items():
            rows.append(
                {
                    "study": gen.get("_study", "generational_qwen_seed7"),
                    "arm": arm,
                    "solver_solves": solves,
                    "llm_calls": gen["llm_calls"].get(arm, 0),
                    "llm_tokens": gen["llm_tokens"].get(arm, 0),
                    "wall_s": gen.get("wall_s"),
                    "model": gen.get("model"),
                    "model_digest": gen.get("model_digest"),
                }
            )
    historical = _load(ROOT / "results" / "v2" / "campaigns" / "matched_qwen_20261018T205937Z" / "matched_pilot.json")
    for arm, solves in historical["solver_solves"].items():
        rows.append(
            {
                "study": "matched_qwen_20261018",
                "arm": arm,
                "solver_solves": solves,
                "llm_calls": historical["llm_calls"].get(arm, 0),
                "llm_tokens": historical["llm_tokens"].get(arm, 0),
                "wall_s": "",
                "model": historical.get("model"),
                "model_digest": "",
            }
        )
    return rows


def _statistics(
    gen: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
    studies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    comparisons = []
    sources = studies if studies is not None else ([gen] if gen is not None else [])
    for source in sources:
        for arm in ("random_evolution", "single_agent", "five_agent"):
            for item in source[arm]:
                decision = item["decision"]
                comparisons.append(
                    {
                        "study": source.get("_study", "generational"),
                        "design": source.get("_design"),
                        "arm": arm,
                        "candidate_id": item["candidate_id"],
                        "wins": decision.get("wins"),
                        "losses": decision.get("losses"),
                        "ties": decision.get("ties"),
                        "accepted": item["accepted"],
                        "reason": decision.get("reason"),
                    }
                )
    promoted = []
    if confirmation is not None:
        for row in confirmation.get("seed_confirmation") or []:
            promoted.append(
                {
                    "arm": row.get("arm"),
                    "candidate_id": row.get("candidate_id"),
                    "three_seed_accepted": row.get("three_seed_accepted"),
                    "reason": row.get("reason"),
                    "wins": row.get("wins"),
                    "losses": row.get("losses"),
                }
            )
    return {
        "design": "paired instance-seed rows; seeds on one instance are not an independent dataset",
        "power": "exploratory",
        "reason": "The new evolution uses five gate instances and discovery seed 7. Extra seeds are measured only for a candidate the seed-7 rule already accepted.",
        "selection_rule": "conservative",
        "robust_rule": "recorded, not used for deployment",
        "seed7_comparisons": comparisons,
        "three_seed_confirmation": promoted,
        "interval": "No interval is reported. The paired sample is too small for a superiority claim.",
    }


def _figure(feasibility: list[dict[str, Any]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    folder = PAPER / "FIGURES"
    folder.mkdir(parents=True, exist_ok=True)
    families = [row["family"] for row in feasibility]
    feasible = [row["feasible"] for row in feasibility]
    total = [row["independent_rows"] for row in feasibility]
    figure, axis = plt.subplots(figsize=(7, 4))
    axis.bar(families, total, color="#d0d7de", label="independent rows")
    axis.bar(families, feasible, color="#1f6feb", label="feasible")
    axis.set_ylabel("rows")
    axis.set_title("Classical development panel at c2de5a0")
    axis.legend()
    figure.tight_layout()
    figure.savefig(folder / "classical_freeze_feasibility.png", dpi=120)
    plt.close(figure)


def _moved(confirmation: dict[str, Any] | None) -> list[str]:
    if confirmation is None:
        return []
    lines = []
    for record in confirmation.get("seed_confirmation") or []:
        if not record.get("candidate_id"):
            continue
        lines.append(
            f"{record['arm']} {record['candidate_id']}: three-seed accepted={record['three_seed_accepted']} "
            f"reason={record['reason']} wins={record.get('wins')} losses={record.get('losses')}"
        )
        for block in record.get("seed_rows") or []:
            for row in block["rows"]:
                if row["instance_id"] == "c101_21":
                    lines.append(
                        f"  seed {block['seed']} c101_21 key={row['objective_key']} "
                        f"within_budget={row.get('completed_within_budget')}"
                    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in confirmation["rows"]:
        grouped.setdefault(f"{row['instance_id']}:{row['seed']}", []).append(row)
    ties = 0
    diffs = 0
    for key, items in grouped.items():
        keys = { _key(item["objective_key"]) for item in items }
        if len(keys) == 1:
            ties += 1
        else:
            diffs += 1
            lines.append(f"  confirmation {key} differs: {keys}")
    lines.append(f"confirmation paired rows tied={ties} differed={diffs}")
    return lines


def _role_split_lines() -> list[str]:
    studies = [
        study
        for study in _studies()
        if study.get("workflow") == "unified_versus_architect_specialist_critic"
    ]
    lines = [
        "## C2. Unified designer versus architect, specialist, and critic",
        "",
        "Each generation calls the architect, the specialist for the one scheduled component, and the critic. Routing, charging, and search rotate across generations. All five roles are not called in the same generation.",
        "",
    ]
    if not studies:
        lines.extend(["No artifact with this workflow is present.", ""])
        return lines
    for study in studies:
        lines.append(
            f"Artifact `{study['_path']}`, discovery seed {study.get('seed')}, wall {study.get('wall_s')}s."
        )
        lines.append(f"Selection: {json.dumps(study.get('selected'))}.")
        lines.append(
            f"Tokens: {json.dumps(study.get('llm_tokens'))}. Solver evaluations: {json.dumps(study.get('solver_solves'))}."
        )
        selected = study.get("selected") or {}
        for arm in ("single_agent", "five_agent"):
            candidate_id = selected.get(arm)
            item = next((row for row in study.get(arm, []) if row.get("candidate_id") == candidate_id), None)
            if item is None:
                lines.append(f"{arm} selected nothing.")
                continue
            insertion = str(item["sources"]["insertion_score"]).strip().replace("\n", " ")
            role = ""
            attribution = item.get("attribution") or []
            if attribution:
                role = str(attribution[0].get("agent_role") or "")
            hiermann = next((row for row in item["rows"] if row["instance_id"] == "c101_21"), None)
            key = None if hiermann is None else hiermann.get("objective_key")
            lines.append(
                f"{arm} {candidate_id} role={role or 'unrecorded'} c101_21={key} insertion=`{insertion}`."
            )
            if item.get("architect_hypothesis"):
                lines.append(f"Architect hypothesis: {item['architect_hypothesis']}")
        lines.append("")
    extra = PAPER / "confirmation_schneider_role_split.json"
    if extra.exists():
        payload = _load(extra)
        lines.append(f"Role-split three-seed file: `{extra.name}`.")
        lines.append(f"Promoted: {payload.get('promoted_policies')}.")
        for row in payload.get("seed_confirmation") or []:
            lines.append(
                f"- {row.get('arm')} {row.get('candidate_id')}: three-seed accepted={row.get('three_seed_accepted')} "
                f"reason={row.get('reason')} wins={row.get('wins')} losses={row.get('losses')}"
            )
        lines.append("")
    return lines


def _report(
    freeze: list[dict[str, Any]],
    feasibility: list[dict[str, Any]],
    gen: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
    commit: str,
) -> str:
    independent = [row for row in freeze if row["independent"]]
    feasible = sum(1 for row in independent if row["feasible"])
    within = sum(1 for row in independent if row["within_parent_budget"])
    family_line = ", ".join(
        f"{row['family']} {row['feasible']}/{row['independent_rows']}" for row in feasibility
    )
    selected = gen["selected"] if gen else {}
    digest = gen.get("model_digest") if gen else None
    promoted = confirmation.get("promoted_policies") if confirmation else None
    classical_confirm = None
    if confirmation is not None:
        classical_confirm = f"{confirmation.get('classical_feasible')}/{confirmation.get('classical_n')}"
    profile = _load(ROOT / "results" / "v2" / "diagnostics" / "large_development" / "profile.json")
    large = [
        f"{row['instance_id']} feasible={row['feasible']} fault={row['fault_family']}"
        for row in profile["rows"]
    ]
    return "\n".join(
        [
            "# VoltForge 2.0 final research report",
            "",
            f"Generated from raw artifacts at `{commit}`.",
            "Native objectives are not averaged across families. Infeasible nominal keys are not results.",
            "Classical improvements are not attributed to the LLM.",
            "",
            "## A. Engineering",
            "",
            "Phases A and B are commit `c2de5a05a9cc27a4aad65f6895231c13b580790a`.",
            "The local suite after that commit was 230 passed. This report does not replace that run.",
            "See `ENGINEERING_VALIDATION.json` for the artifact checks executed with this package.",
            "",
            "## B. Classical backbone",
            "",
            f"Independent development rows at the frozen solver, excluding duplicate `{DUPLICATE}`: {feasible}/{len(independent)} feasible.",
            f"Parent runtime within limit plus 0.05s: {within}/{len(independent)}.",
            f"By family: {family_line}.",
            "Seed-7 gate keys remain the frozen baseline where that baseline was already feasible, including Bezzi `C101-5` at 227.",
            "Bezzi `10-N10` is feasible on seeds 7, 11, and 22 in `results/v2/diagnostics/bezzi_pack/summary.json` and in this freeze.",
            "Those costs are classical pack plus ALNS. They are not the published 22.924 reference and they are not an LLM result.",
            "The historical expanded panel still records the earlier infeasible `10-N10` rows.",
            f"Large Schneider discovery profile, not RC2: {'; '.join(large)}.",
            "That profile is the trace before route-local construction. Seed 7 of c101_21 is then feasible inside 20 seconds at 39 vehicles in results/v2/diagnostics/large_development/c101_21_route_local.json.",
            "The 39-vehicle key is a classical feasible result, not an optimized fleet and not an LLM result.",
            "",
            "## C. Specialist-role schedule, seed 7",
            "",
            f"Design: {gen.get('_design') if gen else 'missing'}.",
            f"Selection: {json.dumps(selected)}.",
            "This is not a unified-agent versus five-role comparison. Both language-model arms used specialist prompts.",
            "The accepted insertion returns are `return max(0, capacity_slack - demand) + abs(delta_distance)` for single_g0 and the same expression plus `float(ready_time > due_time)` for five_g0. That added term is zero when ready_time is at or before due_time.",
            "",
            *_role_split_lines(),
            "",
            "## D. Five-agent evolution",
            "",
            "The 2026-10-18 matched pilot accepted `five_1` on seed 7 and that bundle lost Hiermann `c101_21` on seeds 11 and 22.",
            "It did not beat classical or the random grammar once those seeds were measured.",
            "The 2026-10-19 generational arm uses the same conservative rule, the same gate, and the same candidate count.",
            "Five-agent token use in that schedule is the critic call. The architect was not called.",
            "Equal solver evaluations were enforced. Token counts are measured and are not a matched compute budget.",
            "",
            "## E. What generalizes",
            "",
            "The bullets below are the specialist-schedule confirmation in `confirmation_schneider.json`, not the role-split confirmation in section C2.",
            "The classical default remains the deployed scoring policy.",
            "A grammar candidate can pass the development rule without being an LLM result.",
            * [f"- {line}" for line in _moved(confirmation)],
            f"Policies sent to confirmation after the three-seed decision: {promoted}.",
            f"Classical confirmation rows feasible: {classical_confirm}.",
            "Confirmation ids are `c206C5`, `r202C5`, and `r203C5`. `rc105C5` stays on the development panel and was not used as confirmation.",
            "Schneider RC2 remains the held-out split and was not retuned. The earlier classical held-out file is unchanged: 24/42 feasible, 18/42 feasible and inside budget.",
            "",
            "## F. Quantitative results",
            "",
            "Tables in this directory are regenerated from the raw JSON named in `PROVENANCE.jsonl`.",
            "Published Schneider CPLEX keys live in `evrptw_autolab.evaluation.literature` and are references only.",
            "Some measured keys match those published figures at the reported rounding, including development `r105C5` and confirmation `r203C5`.",
            "Others do not, including development `c101C5` and confirmation `c206C5` and `r202C5`.",
            "No best-known-solution claim is made.",
            f"Model digest recorded for the generational run: {digest}.",
            "",
            "## G. Limitations",
            "",
            "The comparison is exploratory. Five gate instances and one discovery seed do not support a significance claim.",
            "The 14:59 UTC artifact used full-bundle proposals and deployed the first accepted candidate. It is historical.",
            "The 2026-10-19 18:27 and 18:38 UTC runs used specialist role prompts on a rotating component. The five-agent arm added a critic and did not call an architect.",
            "Seed 13 of that same schedule accepted no candidate.",
            "A later run with workflow unified_versus_architect_specialist_critic is reported only when its artifact is present.",
            "Critic text is not a causal explanation.",
            "Route-local construction makes development c101_21 seed 7 feasible inside 20 seconds at 39 vehicles. That fleet is not an optimized result. RC2 was not used to make this change.",
            "Hiermann `c101_21` remains a 20-vehicle classical solution on the frozen seed-7 gate.",
            "FakeBackend output is plumbing and is not model evidence.",
            "",
            "## H. Publication files",
            "",
            "Ready for review as an honest negative-or-limited package: the CSV tables, `STATISTICS.json`, `PROTOCOL.md`, `DATASET_SPLITS.json`, `REPRODUCE.md`, and this report.",
            "Not ready as a superiority paper. No abstract claims that five-agent search beats classical, random, or single-agent search.",
            "",
        ]
    )


def main() -> None:
    commit = _git()
    freeze = _freeze_rows()
    feasibility = _feasibility(freeze)
    studies = _studies()
    gen = _generational()
    confirmation_path = PAPER / "confirmation_schneider.json"
    confirmation = _load(confirmation_path) if confirmation_path.exists() else None
    PAPER.mkdir(parents=True, exist_ok=True)
    _write_csv(PAPER / "CLASSICAL_BASELINES.csv", freeze)
    _write_csv(PAPER / "FEASIBILITY.csv", feasibility)
    _write_csv(PAPER / "ABLATIONS.csv", _historical_ablations())
    comparison_rows: list[dict[str, Any]] = []
    evolution_rows: list[dict[str, Any]] = []
    compute_rows: list[dict[str, Any]] = []
    for index, study in enumerate(studies):
        comparison_rows.extend(_comparison_rows(study))
        evolution_rows.extend(_evolution_rows(study))
        part = _compute(study)
        if index:
            part = [row for row in part if row["study"] != "matched_qwen_20261018"]
        compute_rows.extend(part)
    if not studies:
        compute_rows = _compute(None)
    _write_csv(PAPER / "COMPUTE_COSTS.csv", compute_rows)
    _write_csv(
        PAPER / "TRANSFER_RESULTS.csv",
        [
            {
                "status": "not_run",
                "reason": "Neither the matched pilot nor the generational runner trains on one family and evaluates a frozen bundle on another.",
            }
        ],
    )
    if comparison_rows:
        _write_csv(PAPER / "LLM_METHOD_COMPARISON.csv", comparison_rows)
        _write_csv(PAPER / "EVOLUTION_RESULTS.csv", evolution_rows)
    (PAPER / "STATISTICS.json").write_text(
        json.dumps(_statistics(gen, confirmation, studies), indent=2) + "\n",
        encoding="utf-8",
    )
    split = _load(ROOT / "results" / "manifests" / "split.json")
    panel = _load(ROOT / "results" / "v2" / "manifests" / "development_panel.json")
    (PAPER / "DATASET_SPLITS.json").write_text(
        json.dumps(
            {
                "schneider_split": "results/manifests/split.json",
                "development_panel": [row["instance_id"] for row in panel["instances"]],
                "confirmation_used_after_selection": ["c206C5", "r202C5", "r203C5"],
                "confirmation_overlap_disclosed": sorted(
                    {row["instance_id"] for row in panel["instances"]} & set(split["confirmation_ids"])
                ),
                "heldout_not_used_for_tuning": split["heldout_ids"],
                "duplicate_excluded_from_independent_counts": DUPLICATE,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    from evrptw_autolab.experiments.readiness import engineering_checks

    (PAPER / "ENGINEERING_VALIDATION.json").write_text(
        json.dumps({"git_head": commit, "artifact_checks": engineering_checks(ROOT)}, indent=2) + "\n",
        encoding="utf-8",
    )
    (PAPER / "PROVENANCE.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"git_head": commit, "role": "package"}),
                json.dumps({"path": "results/v2/baselines/classical_frozen_c2de5a0", "role": "classical_freeze"}),
                json.dumps({"path": "results/v2/diagnostics/bezzi_pack/summary.json", "role": "bezzi_10n10"}),
                json.dumps({"path": "results/v2/diagnostics/large_development/profile.json", "role": "large_discovery"}),
                json.dumps({"path": "results/v2/campaigns/generational_qwen_20261019T145936Z/generational.json", "role": "historical_full_bundle_generation"}),
                *[
                    json.dumps({"path": study["_path"], "role": study["_study"], "design": study["_design"], "digest": study.get("model_digest")})
                    for study in studies
                ],
                json.dumps({"path": "results/v2/campaigns/matched_qwen_20261018T205937Z/matched_pilot.json", "role": "historical_matched_pilot", "solver": "27278a1"}),
                json.dumps({"path": "results/v2/paper/heldout_classical.json", "role": "historical_rc2"}),
                json.dumps({"path": "results/v2/paper/confirmation_schneider.json", "role": "confirmation", "present": confirmation is not None}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (PAPER / "PROTOCOL.md").write_text(
        "\n".join(
            [
                "# Protocol",
                "",
                "Selection rule, declared before confirmation: conservative.",
                "Accept only if feasibility is preserved on every development pair, the candidate is not strictly worse on any pair, and it is strictly better on at least one pair.",
                "A candidate whose probe scores do not change is rejected as `no_decision_change`.",
                "The robust one-third rule is recorded and is not the deployment rule.",
                "Search arms receive the same candidate count, the same gate instances, the same per-instance time limits, and the same evaluator.",
                "Each generation replaces one scheduled component of the accepted parent. The schedule cycles insertion, station, then removal.",
                "Generation 0 receives no fitness feedback. Later generations do.",
                "Among conservatively accepted candidates, the one with the most wins is deployed. An earlier generation wins a tie.",
                "The critic receives the classical objective keys. It does not add a solver evaluation.",
                "The 2026-10-19 18:27 and 18:38 UTC artifacts use specialist prompts. Five-agent's extra call in those artifacts is the critic, not an architect.",
                "The current code workflow is unified_versus_architect_specialist_critic. It is reported only from artifacts that record that workflow.",
                "Random, single-agent, and five-agent search use the same expression language and the same scheduled component.",
                "Confirmation ids `c206C5`, `r202C5`, and `r203C5` are loaded only after the three-seed decision file is written.",
                "If no learned policy passes that decision, confirmation is classical only.",
                "Schneider RC2 is not used to choose a policy.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (PAPER / "REPRODUCE.md").write_text(
        "\n".join(
            [
                "# Reproduce",
                "",
                "From the repository root, with the local environment:",
                "",
                "```",
                "uv run pytest -q",
                "uv run ruff check src tests",
                "uv run mypy src",
                "uv run voltforge validate-data",
                "uv run voltforge research-ready --checks-only",
                "uv run python scripts/freeze_classical.py",
                "uv run python scripts/profile_large_dev.py",
                "uv run python src/evrptw_autolab/experiments/generational_compare.py --fake --micro --candidates 2",
                "uv run python src/evrptw_autolab/experiments/generational_compare.py --seed 7 --candidates 4",
                "uv run python scripts/confirm_after_selection.py",
                "uv run python scripts/build_paper_package.py",
                "```",
                "",
                "The live command needs local Ollama and `qwen3-coder:30b`.",
                "The fake command is a plumbing check. Do not cite it as model evidence.",
                "Do not overwrite `results/v2/baselines/classical/run_27278a1_seed7_20261018T203033Z` or the historical campaign directories.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _figure(feasibility)
    (PAPER / "FINAL_RESEARCH_REPORT.md").write_text(
        _report(freeze, feasibility, gen, confirmation, commit),
        encoding="utf-8",
    )
    prior = PAPER / "RESULTS.md"
    note = (
        "\n\n## Correction, 2026-10-19\n\n"
        "The Bezzi `10-N10` paragraph above describes the solver before commit `c2de5a0`. "
        "That commit makes seeds 7, 11, and 22 feasible inside 12 seconds. "
        "The costs are in `results/v2/diagnostics/bezzi_pack/summary.json`. "
        "They are classical results, not LLM results, and they do not match the published 22.924 reference. "
        "The expanded-panel rows from the older solver stay infeasible on purpose.\n"
    )
    text = prior.read_text(encoding="utf-8")
    if "Correction, 2026-10-19" not in text:
        prior.write_text(text + note, encoding="utf-8")
    print({"freeze_rows": len(freeze), "generational": gen is not None, "confirmation": confirmation is not None})


if __name__ == "__main__":
    main()
