"""Select the strong local coding-model anchor from the frozen pilot rows."""
from __future__ import annotations

import json
import sys
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
    return bool(row.get("schneider_c5")) or str(row.get("deepest_gate") or "") == "schneider_c5" or int(
        row.get("curriculum_g4_best") or 0
    ) > 0 and _depth(row) >= 5


def _load_rows() -> list[dict]:
    rows = []
    for path in sorted(PILOT.glob("*_seed*.json")):
        if path.name.endswith("_evolution.json"):
            continue
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("experiment") not in {None, "strong_model_pilot", "five_agent_synthesis"}:
            if "strong" not in str(row.get("experiment") or ""):
                continue
        rows.append(row)
    return rows


def select(rows: list[dict]) -> tuple[str, dict]:
    by_profile: dict[str, list[dict]] = {}
    for row in rows:
        profile = str(row.get("profile") or "")
        if not profile:
            continue
        by_profile.setdefault(profile, []).append(row)

    ranked = []
    for profile, group in by_profile.items():
        n_g4 = sum(1 for r in group if _reached_g4(r) or int(r.get("curriculum_g4_best") or 0) > 0 and str(r.get("deepest_gate")) == "schneider_c5")
        # Prefer explicit deepest_gate == schneider_c5 for "reaching G4"
        n_g4 = sum(1 for r in group if str(r.get("deepest_gate") or "") == "schneider_c5" or bool(r.get("schneider_c5")))
        n_4of4 = sum(1 for r in group if bool(r.get("schneider_c5")) or int(r.get("curriculum_g4_best") or 0) >= 4)
        best_curr = max((int(r.get("curriculum_g4_best") or r.get("best_g4_feasible") or 0) for r in group), default=0)
        # Only count curriculum G4 if they actually worked on G4
        best_curr_gated = 0
        for r in group:
            if str(r.get("deepest_gate") or "") == "schneider_c5" or bool(r.get("schneider_c5")):
                best_curr_gated = max(best_curr_gated, int(r.get("curriculum_g4_best") or r.get("best_g4_feasible") or 0))
            elif int(r.get("curriculum_g4_best") or 0) > 0 and str(r.get("deepest_gate") or "") == "schneider_c5":
                best_curr_gated = max(best_curr_gated, int(r.get("curriculum_g4_best") or 0))
        n_g3 = sum(1 for r in group if _depth(r) >= 4 or bool(r.get("multi_customer")))
        tokens = sum(int(r.get("tokens") or 0) for r in group)
        ranked.append(
            (
                n_g4,
                n_4of4,
                best_curr_gated if best_curr_gated else (best_curr if n_g4 else 0),
                n_g3,
                -tokens,
                profile,
                {
                    "profile": profile,
                    "model": group[0].get("model"),
                    "n_seeds": len(group),
                    "n_reached_g4": n_g4,
                    "n_4of4": n_4of4,
                    "best_curriculum_g4": best_curr_gated if n_g4 else 0,
                    "n_reached_g3": n_g3,
                    "total_tokens": tokens,
                },
            )
        )
    if not ranked:
        raise SystemExit("no pilot rows to select from")
    ranked.sort(reverse=True)
    winner = ranked[0]
    return winner[5], winner[6]


def main() -> None:
    rows = _load_rows()
    profile, summary = select(rows)
    decision = {
        "selected_strong_model": profile,
        "rule": [
            "n_seeds reaching G4 (deepest_gate=schneider_c5)",
            "n 4/4 successes",
            "best curriculum_g4_best",
            "n reaching G3",
            "lower total tokens",
        ],
        "summary": summary,
        "all_profiles": [],
    }
    # Recompute all profile summaries for the report
    _, _ = select(rows)
    by_profile: dict[str, list[dict]] = {}
    for row in rows:
        by_profile.setdefault(str(row.get("profile")), []).append(row)
    for profile_id, group in sorted(by_profile.items()):
        decision["all_profiles"].append(
            {
                "profile": profile_id,
                "model": group[0].get("model"),
                "seeds": [
                    {
                        "seed": r.get("seed"),
                        "deepest_gate": r.get("deepest_gate"),
                        "curriculum_g4_best": r.get("curriculum_g4_best", r.get("best_g4_feasible")),
                        "posthoc_g4_score": r.get("posthoc_g4_score"),
                        "schneider_c5": r.get("schneider_c5"),
                        "tokens": r.get("tokens"),
                        "llm_calls": r.get("llm_calls"),
                        "solver_hash": r.get("solver_hash"),
                    }
                    for r in sorted(group, key=lambda x: int(x.get("seed") or 0))
                ],
            }
        )
    out = PILOT / "SELECTION.json"
    out.write_text(json.dumps(decision, indent=2), encoding="utf-8")
    cfg = yaml.safe_load(EXPERIMENTS.read_text(encoding="utf-8")) or {}
    runs = list((cfg.get("five_agent_synthesis") or {}).get("runs") or [])
    runs = [r for r in runs if r.get("profile") != profile]
    # Ensure selected strong model appears with seeds 11..55
    runs.append({"profile": profile, "seeds": [11, 22, 33, 44, 55], "role": "selected_strong_model"})
    cfg.setdefault("five_agent_synthesis", {})["runs"] = runs
    cfg["five_agent_synthesis"]["selected_strong_model"] = profile
    cfg.setdefault("solver_evolution", {})["profile"] = profile
    cfg["solver_evolution"]["selected_strong_model"] = profile
    EXPERIMENTS.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    print(json.dumps({"selected_strong_model": profile, "written": str(out)}, indent=2))


if __name__ == "__main__":
    main()
