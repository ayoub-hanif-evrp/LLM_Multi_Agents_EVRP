"""Retry only the LLM proposal arms and merge into evidence_discovery.json."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from evrptw_autolab.discovery.controller import CallBudget
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.llm.registry import availability, make_backend, resolve_profile

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "experiment_evidence_discovery",
    Path(__file__).resolve().parent / "experiment_evidence_discovery.py",
)
assert _SPEC and _SPEC.loader
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["experiment_evidence_discovery"] = _MOD
_SPEC.loader.exec_module(_MOD)

CALLS_PER_PROPOSAL = _MOD.CALLS_PER_PROPOSAL
HEADROOM = _MOD.HEADROOM
MAX_PROPOSALS = _MOD.MAX_PROPOSALS
MODEL_ID = _MOD.MODEL_ID
OUT = _MOD.OUT
_discover_one = _MOD._discover_one
_evaluate_operator = _MOD._evaluate_operator
_evidence_blob = _MOD._evidence_blob
_single_llm_proposal = _MOD._single_llm_proposal


def main() -> None:
    data = json.loads(OUT.read_text(encoding="utf-8"))
    headroom = json.loads(HEADROOM.read_text(encoding="utf-8"))
    evidence = _evidence_blob(list(headroom.get("training_evidence") or []))
    profile = resolve_profile(MODEL_ID)
    if availability(profile) != "installed":
        raise RuntimeError(f"model {MODEL_ID} not installed")
    backend = make_backend(profile)

    proposals = []
    for index in range(MAX_PROPOSALS):
        budget = CallBudget(CALLS_PER_PROPOSAL, model=profile.model, max_tokens=12_000, wall_s=600.0)
        result = _discover_one(backend, evidence, proposal_index=index, budget=budget)
        proposals.append(result)
        print(
            "proposal",
            index,
            result.get("status"),
            result.get("error") or (result.get("operator") or {}).get("candidate_scoring_policy"),
            flush=True,
        )

    single_budget = CallBudget(1, model=profile.model, max_tokens=4_000, wall_s=300.0)
    single = _single_llm_proposal(backend, evidence, single_budget)
    print(
        "single",
        single.get("status"),
        single.get("error") or (single.get("operator") or {}).get("candidate_scoring_policy"),
        flush=True,
    )

    data["proposals"] = proposals
    data["single_llm_proposal"] = single
    data["evaluations"] = [
        row
        for row in data["evaluations"]
        if not str(row["name"]).startswith("multi_role") and row["name"] != "single_llm"
    ]

    if single.get("status") == "ok":
        evaluation = _evaluate_operator("single_llm", OperatorSpec.model_validate(single["operator"]))
        data["evaluations"].append(evaluation)
        print("eval single_llm", evaluation["gate"], evaluation["wins"], flush=True)

    for proposal in proposals:
        if proposal.get("status") != "ok":
            continue
        evaluation = _evaluate_operator(
            f"multi_role_{proposal['proposal_index']}",
            OperatorSpec.model_validate(proposal["operator"]),
        )
        evaluation["proposal_index"] = proposal["proposal_index"]
        data["evaluations"].append(evaluation)
        print("eval", evaluation["name"], evaluation["gate"], evaluation["wins"], flush=True)

    beneficial = [row["name"] for row in data["evaluations"] if row["gate"] == "beneficial"]
    llm_beneficial = [name for name in beneficial if name.startswith("multi_role") or name == "single_llm"]
    data["beneficial_operators"] = beneficial
    data["llm_beneficial_operators"] = llm_beneficial
    if llm_beneficial:
        data["research_signal"] = "go"
    elif any(name.startswith("handcrafted") or name == "random_valid" for name in beneficial):
        data["research_signal"] = "search_space_go_llm_no_go"
    else:
        data["research_signal"] = "no_go"
    data["llm_budget"]["total_calls"] = sum(int(p.get("llm_calls") or 0) for p in proposals) + int(
        single.get("llm_calls") or 0
    )
    data["llm_budget"]["prompt_tokens"] = sum(int(p.get("prompt_tokens") or 0) for p in proposals) + int(
        single_budget.prompt_tokens
    )
    data["llm_budget"]["completion_tokens"] = sum(
        int(p.get("completion_tokens") or 0) for p in proposals
    ) + int(single_budget.completion_tokens)
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("wrote", OUT, "signal=", data["research_signal"], "llm_beneficial=", llm_beneficial, flush=True)


if __name__ == "__main__":
    main()
