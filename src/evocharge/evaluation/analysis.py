"""Post-hoc analysis answering M8 candidate-specific questions."""

from __future__ import annotations

from collections import Counter
from typing import Any


def summarize_behavioral_probes(probes: list[dict[str, Any]]) -> dict[str, Any]:
    effects: list[dict[str, Any]] = []
    for p in probes:
        eff = p.get("effect")
        if isinstance(eff, dict):
            effects.append(eff)
    by_instance: dict[str, list[dict[str, Any]]] = {}
    for p in probes:
        by_instance.setdefault(str(p.get("instance")), []).append(p)

    changed_instances = []
    inert_instances = []
    for inst, rows in by_instance.items():
        any_change = False
        for row in rows:
            eff = row.get("effect") if isinstance(row.get("effect"), dict) else {}
            assert isinstance(eff, dict)
            if any(
                bool(eff.get(k))
                for k in (
                    "customer_sequence_changed",
                    "station_sequence_changed",
                    "charging_decision_changed",
                    "route_assignment_changed",
                )
            ):
                any_change = True
                break
        if any_change:
            changed_instances.append(inst)
        else:
            inert_instances.append(inst)

    prim_counts: Counter[str] = Counter()
    for eff in effects:
        for pid in eff.get("plan_primitives") or []:
            prim_counts[str(pid)] += 1

    station_attempts = sum(
        1
        for e in effects
        if "plan_station_replacement" in (e.get("plan_primitives") or [])
    )
    station_changed = sum(1 for e in effects if bool(e.get("station_sequence_changed")))
    charging_changed = sum(1 for e in effects if bool(e.get("charging_decision_changed")))
    customer_changed = sum(1 for e in effects if bool(e.get("customer_sequence_changed")))
    identical_station_replace = 0
    for p in probes:
        plan = p.get("plan") if isinstance(p.get("plan"), dict) else {}
        assert isinstance(plan, dict)
        for action in plan.get("actions") or []:
            if not isinstance(action, dict):
                continue
            args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
            assert isinstance(args, dict)
            if action.get("primitive_id") == "plan_station_replacement":
                old = args.get("old_station_id") or args.get("station_id")
                new = args.get("new_station_id")
                if old is not None and new is not None and str(old) == str(new):
                    identical_station_replace += 1

    return {
        "n_probes": len(probes),
        "n_with_effect": len(effects),
        "instances_with_any_change": changed_instances,
        "instances_fully_inert": inert_instances,
        "primitive_counts": dict(prim_counts),
        "station_replacement_attempts_in_effects": station_attempts,
        "successful_station_sequence_changes": station_changed,
        "charging_pattern_changes": charging_changed,
        "customer_sequence_changes": customer_changed,
        "identical_old_new_station_replacements_in_rejected_or_raw": identical_station_replace,
        "inert_rate": (
            sum(1 for p in probes if p.get("inert")) / len(probes) if probes else None
        ),
    }



def answer_candidate_questions(
    *,
    candidate_id: str,
    category: str,
    behavioral: dict[str, Any],
    classification: dict[str, Any],
    paired_deltas: list[float],
    analogue_similarity: float | None,
) -> dict[str, Any]:
    probes = list(behavioral.get("behavioral_probes") or [])
    beh = summarize_behavioral_probes(probes)
    mean_delta = sum(paired_deltas) / len(paired_deltas) if paired_deltas else None
    answers: dict[str, Any] = {
        "candidate_id": candidate_id,
        "category": category,
        "classification_label": classification.get("label"),
        "behavioral_summary": beh,
        "mean_paired_distance_delta_vs_baseline": mean_delta,
        "analogue_similarity_sign_agreement": analogue_similarity,
        "questions": {},
    }

    if "destroy" in category or "h2" in candidate_id.lower():
        answers["questions"] = {
            "why_changed_some_fixtures_not_others": (
                "Changed instances: "
                + ", ".join(beh["instances_with_any_change"] or ["none"])
                + "; inert instances: "
                + ", ".join(beh["instances_fully_inert"] or ["none"])
                + ". Fixture structure and removal targets likely differ; "
                "absence of change on one fixture is recorded, not claimed causal."
            ),
            "differs_from_existing_removal_operators": (
                f"Analogue sign agreement={analogue_similarity}; "
                "REDUNDANT only if agreement is high and classification says so. "
                f"Observed primitives={beh['primitive_counts']}."
            ),
            "regret_reinsertion_vs_removal_logic": (
                "Plans that include plan_regret_reinsertion apply both removal and "
                "reinsertion inside the candidate; paired ALNS cannot isolate gain "
                "source without an ablation that disables reinsertion."
            ),
            "improves_or_only_changes_route": (
                f"mean_paired_distance_delta_vs_baseline={mean_delta}; "
                "negative means shorter distance on average under this short budget. "
                "Behavioral change without consistent negative delta is change-only."
            ),
        }
    elif "charging" in category or "h3" in candidate_id.lower():
        answers["questions"] = {
            "station_replacement_rejected": (
                "Count rejected probes separately; applied station replacements in "
                f"effects={beh['station_replacement_attempts_in_effects']}."
            ),
            "replacement_station_identical": (
                f"identical_old_new_observed={beh['identical_old_new_station_replacements_in_rejected_or_raw']}"
            ),
            "charging_repair_restored_original": (
                f"station_sequence_changes={beh['successful_station_sequence_changes']}, "
                f"charging_pattern_changes={beh['charging_pattern_changes']}. "
                "If replacements attempted but both remain 0, repair likely restored "
                "an equivalent pattern or replacement was a no-op."
            ),
            "no_alternative_compatible_station": (
                "Not directly observable without enumerating feasible stations; "
                "inertness with nonempty replace plans suggests instance/structure "
                "or repair cancellation rather than proven absence of alternatives."
            ),
            "inert_due_to_logic_or_fixtures": (
                f"inert_rate={beh['inert_rate']}; "
                "classification="
                f"{classification.get('label')}. "
                "Treat as valid-but-inert on these fixtures pending broader instances."
            ),
        }
    else:
        answers["questions"] = {
            "segment_action_occurred": (
                f"primitive_counts={beh['primitive_counts']}; "
                f"customer_sequence_changes={beh['customer_sequence_changes']}"
            ),
            "charging_reconstruction_cancelled_route_change": (
                f"customer_changes={beh['customer_sequence_changes']}, "
                f"charging_changes={beh['charging_pattern_changes']}, "
                f"inert_rate={beh['inert_rate']}. "
                "If segment primitives present but sequences unchanged after apply, "
                "reconstruction/repair may have cancelled the move."
            ),
            "primitive_ordering_ineffective": (
                "Ordering effects are inferred only when intermediate states differ; "
                "final-state probes alone cannot fully prove ordering failure."
            ),
            "hypothesis_needs_missing_conditions": (
                "Three anchored Cus100 fixtures may lack the congestion/charging "
                "conditions hypothesized; record as fixture-limited evidence."
            ),
        }
    return answers
