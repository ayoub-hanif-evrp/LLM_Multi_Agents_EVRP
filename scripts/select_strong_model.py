"""Select the strong local coding-model anchor from the frozen pilot rows."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "results" / "strong_pilot"
EXPERIMENTS = ROOT / "configs" / "experiments.yaml"

STAGE_ORDER = ("executable", "routing", "charging", "multi_customer", "schneider_c5")


def _depth(row: dict) -> int:
    deepest = str(row.get("deepest_gate") or "")
    if deepest in STAGE_ORDER:
        return STAGE_ORDER.index(deepest) + 1
    score = 0
    for key in STAGE_ORDER:
        if row.get(key):
            score += 1
        else:
            break
    return score


def _reached_g4(row: dict) -> bool:
    """G4 was entered during curriculum (may still fail the stage)."""
    if bool(row.get("schneider_c5")) or str(row.get("deepest_gate") or "") == "schneider_c5":
        return True
    # curriculum_g4_best is updated only while the active stage is schneider_c5
    if int(row.get("curriculum_g4_best") or 0) > 0:
        return True
    return str(row.get("failure_reason") or "").startswith("G4 ")


def _load_rows() -> list[dict]:
    rows = []
    for path in sorted(PILOT.glob("*_seed*.json")):
        if path.name.endswith("_evolution.json"):
            continue
        row = json.loads(path.read_text(encoding="utf-8"))
        exp = str(row.get("experiment") or "")
        if exp and "strong" not in exp and exp != "five_agent_synthesis":
            continue
        rows.append(row)
    return rows


def select(rows: list[dict]) -> tuple[str, dict, list[dict]]:
    by_profile: dict[str, list[dict]] = {}
    for row in rows:
        profile = str(row.get("profile") or "")
        if profile:
            by_profile.setdefault(profile, []).append(row)

    ranked: list[tuple] = []
    summaries: list[dict] = []
    for profile, group in by_profile.items():
        n_g4 = sum(1 for r in group if _reached_g4(r))
        n_4of4 = sum(
            1
            for r in group
            if bool(r.get("schneider_c5")) or int(r.get("curriculum_g4_best") or 0) >= 4
        )
        best_curr = max((int(r.get("curriculum_g4_best") or 0) for r in group if _reached_g4(r)), default=0)
        n_g3 = sum(1 for r in group if _depth(r) >= 4 or bool(r.get("multi_customer")))
        tokens = sum(int(r.get("tokens") or 0) for r in group)
        summary = {
            "profile": profile,
            "model": group[0].get("model"),
            "n_seeds": len(group),
            "n_reached_g4": n_g4,
            "n_4of4": n_4of4,
            "best_curriculum_g4": best_curr,
            "n_reached_g3": n_g3,
            "total_tokens": tokens,
        }
        summaries.append(summary)
        ranked.append((n_g4, n_4of4, best_curr, n_g3, -tokens, profile, summary))
    if not ranked:
        raise SystemExit("no pilot rows to select from")
    ranked.sort(reverse=True)
    summaries.sort(key=lambda s: s["profile"])
    winner = ranked[0]
    return winner[5], winner[6], summaries


def main() -> None:
    rows = _load_rows()
    profile, summary, summaries = select(rows)
    decision = {
        "selected_strong_model": profile,
        "rule": [
            "n seeds that entered G4 (curriculum_g4_best>0 or schneider_c5)",
            "n 4/4 successes",
            "best curriculum_g4_best",
            "n reaching G3",
            "lower total tokens",
        ],
        "summary": summary,
        "ranking": summaries,
        "all_profiles": [
            {
                "profile": pid,
                "model": group[0].get("model"),
                "seeds": [
                    {
                        "seed": r.get("seed"),
                        "deepest_gate": r.get("deepest_gate"),
                        "curriculum_g4_best": r.get("curriculum_g4_best"),
                        "posthoc_g4_score": r.get("posthoc_g4_score"),
                        "schneider_c5": r.get("schneider_c5"),
                        "tokens": r.get("tokens"),
                        "llm_calls": r.get("llm_calls"),
                        "solver_hash": r.get("solver_hash"),
                    }
                    for r in sorted(group, key=lambda x: int(x.get("seed") or 0))
                ],
            }
            for pid, group in sorted(
                {
                    str(r.get("profile")): [x for x in rows if str(x.get("profile")) == str(r.get("profile"))]
                    for r in rows
                }.items()
            )
        ],
    }
    (PILOT / "SELECTION.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")

    cfg = yaml.safe_load(EXPERIMENTS.read_text(encoding="utf-8")) or {}
    runs = list((cfg.get("five_agent_synthesis") or {}).get("runs") or [])
    runs = [r for r in runs if r.get("profile") != profile]
    runs.append({"profile": profile, "seeds": [11, 22, 33, 44, 55], "role": "selected_strong_model"})
    cfg.setdefault("five_agent_synthesis", {})["runs"] = runs
    cfg["five_agent_synthesis"]["selected_strong_model"] = profile
    cfg.setdefault("solver_evolution", {})["profile"] = profile
    cfg["solver_evolution"]["selected_strong_model"] = profile
    EXPERIMENTS.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    print(json.dumps({"selected_strong_model": profile, "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
