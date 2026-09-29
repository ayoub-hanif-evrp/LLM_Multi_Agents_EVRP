"""Fake-model tests for transactional synthesis, gates, feedback, and token accounting."""
from __future__ import annotations

import json
from pathlib import Path

from evrptw_autolab.agents.search_engineer import SearchEngineer
from evrptw_autolab.evolution.evaluate import find_hardcoded_node_ids
from evrptw_autolab.llm.usage import LLMUsage, UsageLog
from evrptw_autolab.problem.types import EvaluationReport
from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.synthesis.from_scratch import (
    evaluate_through,
    format_runtime_error,
    precheck_source,
    run_from_scratch,
)

ARCHITECT = json.dumps(
    {
        "hypothesis": "produce one solver.py for the current gate",
        "target": "SEARCH",
        "evidence": ["gate"],
        "agents_to_activate": ["search"],
        "files_or_components": ["solver.py"],
        "success_criteria": ["pass the current gate"],
        "constraint_ledger": [],
        "budget": {},
    }
)
CRITIC = json.dumps(
    {
        "decision": "REVISE",
        "primary_cause": "CRITIC_TOKEN_91",
        "evidence": ["executed the trial"],
        "credited_components": [],
        "blamed_components": ["solve"],
        "next_target": "SEARCH",
        "lesson": "CRITIC_TOKEN_91",
    }
)
EMPTY = (
    "def solve(instance, seed: int, time_limit_s: float):\n"
    "    return {'routes': [], 'metadata': {}}\n"
)
CRASH = (
    "def solve(instance, seed: int, time_limit_s: float):\n"
    "    raise NameError('missing_name_xyz')\n"
)
FRAGMENT = "def specialist_fragment(instance):\n    return []\n"


class Scripted:
    def __init__(self, handler) -> None:  # noqa: ANN001
        self.handler = handler
        self.prompts: list[tuple[str, str]] = []

    def complete(self, *, prompt: str, role: str, temperature: float, model: str, json_mode: bool = True) -> str:
        self.prompts.append((role, prompt))
        return self.handler(role, prompt)


def test_runtime_feedback_keeps_the_exception() -> None:
    error = (
        "Traceback (most recent call last):\n"
        '  File "solver.py", line 2, in solve\n'
        "NameError: missing_name_xyz\n"
        "CONTRACT: banner\n"
    )
    source = "def solve(instance, seed, time_limit_s):\n    raise NameError('missing_name_xyz')\n"
    info = format_runtime_error(error, source)
    assert info["exception_type"] == "NameError"
    assert "missing_name_xyz" in info["exception_message"]
    assert "NameError: missing_name_xyz" in info["traceback_tail"]
    assert "2:" in info["source_context"]


def test_hardcoded_instance_id_rejected_ordinary_strings_kept() -> None:
    ordinary = (
        "def solve(instance, seed: int, time_limit_s: float):\n"
        "    return {'routes': [], 'metadata': {'seed': seed, 'status': 'OK'}}\n"
    )
    assert find_hardcoded_node_ids(ordinary, known_ids={"D0", "C1"}) == []
    assert precheck_source(ordinary, {"D0", "C1"}) is None
    hardcoded = (
        "def solve(instance, seed: int, time_limit_s: float):\n"
        "    return {'routes': [['D0', 'C1', 'D0']], 'metadata': {}}\n"
    )
    blocked = precheck_source(hardcoded, {"D0", "C1", "S0"})
    assert blocked is not None
    assert blocked["category"] == "GENERALITY"
    assert "D0" in blocked["failure_reason"]
    assert "C1" in blocked["failure_reason"]


def test_later_gate_cannot_regress_earlier_gate(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    def fake_run(solver_dir, instance, seed=0, limits=None):  # noqa: ANN001
        if "g1" in instance.instance_id:
            return EvaluationReport(
                parse_ok=True,
                feasible=False,
                first_fault={"family": "VISIT", "node_id": "C1", "route_index": 0, "detail": "missing"},
            )
        return EvaluationReport(
            parse_ok=True,
            feasible=True,
            vehicles=1,
            total_distance=1.0,
            first_fault={"family": "OK", "node_id": "", "route_index": -1, "detail": ""},
        )

    monkeypatch.setattr("evrptw_autolab.synthesis.from_scratch.run_solver", fake_run)
    solver = tmp_path / "solver"
    solver.mkdir()
    (solver / "solver.py").write_text(EMPTY, encoding="utf-8")
    result = evaluate_through(solver, "charging", limits=RunLimits(wall_clock_s=5), panel=[])
    assert result["ok"] is False
    assert result["failed_stage"] == "routing"
    assert result["category"] == "VISIT"


def test_failed_trial_keeps_committed_and_feeds_critic(tmp_path: Path) -> None:
    def handler(role: str, prompt: str) -> str:
        if role == "architect":
            return ARCHITECT
        if role == "critic":
            return CRITIC
        if role == "routing":
            return FRAGMENT
        if '"stage": "executable"' in prompt:
            return EMPTY
        return CRASH

    backend = Scripted(handler)
    report = run_from_scratch(
        mode="five_agent",
        model="fake",
        backend=backend,
        workspace=tmp_path / "ws",
        max_llm_calls=8,
    )
    committed = (tmp_path / "ws" / "committed" / "solver.py").read_text(encoding="utf-8")
    assert "NameError" not in committed
    assert "def solve" in committed
    assert not (tmp_path / "ws" / "committed" / "routing.py").exists()
    roles = [role for role, _ in backend.prompts]
    assert roles.count("routing") == 1
    assert roles.count("architect") == 2
    search_prompts = [prompt for role, prompt in backend.prompts if role == "search"]
    assert "NameError" in search_prompts[-1]
    assert "missing_name_xyz" in search_prompts[-1]
    assert "CRITIC_TOKEN_91" in search_prompts[-1]
    assert report["solver_hash"]
    assert report["failure_category"] in {"RUNTIME", "BUDGET", "VISIT"}


def test_single_agent_receives_runtime_diagnostics(tmp_path: Path) -> None:
    def handler(role: str, prompt: str) -> str:
        if role == "single" and "missing_name_xyz" not in prompt:
            return CRASH
        return EMPTY

    backend = Scripted(handler)
    run_from_scratch(
        mode="single_agent",
        model="fake",
        backend=backend,
        workspace=tmp_path / "single",
        max_llm_calls=2,
    )
    single_prompts = [prompt for role, prompt in backend.prompts if role == "single"]
    assert len(single_prompts) == 2
    assert "NameError" in single_prompts[1]
    assert "missing_name_xyz" in single_prompts[1]
    assert "family" in single_prompts[1]


def test_physical_calls_and_tokens_both_count(tmp_path: Path) -> None:
    class TwoGenerations:
        def complete(self, *, prompt: str, role: str, temperature: float, model: str, json_mode: bool = True) -> str:
            self.pending_usages = [
                LLMUsage(
                    model_id="qwen2.5-coder:7b",
                    provider="ollama",
                    role=role,
                    latency_s=0.2,
                    prompt_tokens=10,
                    completion_tokens=4,
                    repair=False,
                    seed=11,
                    model_tag="qwen2.5-coder:7b",
                    digest="digest-a",
                ),
                LLMUsage(
                    model_id="qwen2.5-coder:7b",
                    provider="ollama",
                    role=role,
                    latency_s=0.3,
                    prompt_tokens=8,
                    completion_tokens=3,
                    repair=True,
                    seed=11,
                    model_tag="qwen2.5-coder:7b",
                    digest="digest-a",
                ),
            ]
            return EMPTY

    log = UsageLog(tmp_path / "llm_calls.jsonl")
    agent = SearchEngineer(TwoGenerations(), model="qwen2.5-coder:7b", temperature=0.2, usage_log=log)
    agent.write_python({"instruction": "repair"}, filename="solver.py", marker="def solve")
    rows = log.all()
    assert len(rows) == 2
    assert rows[1]["repair"] is True
    assert sum(int(row["prompt_tokens"]) + int(row["completion_tokens"]) for row in rows) == 25
    assert rows[0]["model_tag"] == "qwen2.5-coder:7b"
    assert rows[0]["seed"] == 11
