import json

import pytest
from pydantic import ValidationError

from evrptw_autolab.agents.base import extract_json
from evrptw_autolab.agents.schemas import ArchitectPlan, CodeProposal, CriticDecision


def test_valid_architect_json() -> None:
    plan = ArchitectPlan.model_validate(
        {
            "hypothesis": "bootstrap",
            "target": "BOOTSTRAP",
            "evidence": [],
            "agents_to_activate": ["routing", "charging", "search", "critic"],
            "files_or_components": ["solver.py"],
            "success_criteria": ["runs"],
            "budget": {"max_proposals": 2},
        }
    )
    assert plan.target == "BOOTSTRAP"


def test_invalid_schema_rejects() -> None:
    with pytest.raises(ValidationError):
        ArchitectPlan.model_validate({"hypothesis": "x"})


def test_codeproposal_fills_missing_fields() -> None:
    proposal = CodeProposal.model_validate({"proposal_id": "I012", "role": "search"})
    assert proposal.change_type == "REPLACE_FILE"
    assert proposal.files == []
    assert proposal.hypothesis == ""


def test_extract_json_from_fence() -> None:
    payload = extract_json("```json\n{\"hypothesis\": \"h\", \"target\": \"BOOTSTRAP\", \"evidence\": [], \"agents_to_activate\": [], \"files_or_components\": [], \"success_criteria\": []}\n```")
    ArchitectPlan.model_validate(payload)


def test_critic_schema() -> None:
    decision = CriticDecision.model_validate(
        {
            "decision": "RETAIN",
            "primary_cause": "improved",
            "evidence": ["F1"],
            "credited_components": ["charging.py"],
            "blamed_components": [],
            "next_target": "NONE",
            "lesson": "energy repair restored feasibility",
        }
    )
    assert decision.decision == "RETAIN"
    json.dumps(decision.model_dump())


def test_codefile_coerces_modify_to_replace() -> None:
    from evrptw_autolab.agents.schemas import CodeFile

    file = CodeFile.model_validate({"path": "charging.py", "operation": "modify", "content": "x=1"})
    assert file.operation == "replace"


def test_handshake_verdict_from_critic_decision() -> None:
    from evrptw_autolab.agents.base import coerce_schema_payload
    from evrptw_autolab.agents.schemas import HandshakeVerdict

    payload = coerce_schema_payload(
        "HandshakeVerdict",
        {
            "decision": "REVISE",
            "primary_cause": "syntax",
            "evidence": ["f0"],
            "next_target": "SEARCH",
            "lesson": "rewrite solver.py",
        },
    )
    verdict = HandshakeVerdict.model_validate(payload)
    assert verdict.verdict == "RETURN"
    assert verdict.owner == "SEARCH"


def test_architect_coerce_missing_hypothesis() -> None:
    from evrptw_autolab.agents.base import coerce_schema_payload

    payload = coerce_schema_payload(
        "ArchitectPlan",
        {"solver_id": "S000", "constraint_ledger": [], "target": "SEARCH"},
    )
    plan = ArchitectPlan.model_validate(payload)
    assert plan.hypothesis
    assert plan.target == "SEARCH"


def test_critic_coerce_partial_deepseek_style() -> None:
    from evrptw_autolab.agents.base import coerce_schema_payload

    payload = coerce_schema_payload(
        "CriticDecision",
        {
            "decision": "REVERT",
            "primary_cause": "crash",
            "evidence": [{"child": True, "error": "no module named physics"}],
        },
    )
    decision = CriticDecision.model_validate(payload)
    assert decision.decision == "REVERT"
    assert decision.next_target == "SEARCH"
    assert decision.lesson
    assert isinstance(decision.evidence[0], str)
