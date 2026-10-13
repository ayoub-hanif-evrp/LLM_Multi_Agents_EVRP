"""Fake-model tests for patch-based multi-candidate synthesis and G4 scoring."""
from __future__ import annotations

import json
from pathlib import Path

from evrptw_autolab.agents.search_engineer import SearchEngineer
from evrptw_autolab.evolution.evaluate import find_hardcoded_node_ids
from evrptw_autolab.llm.usage import LLMUsage, UsageLog
from evrptw_autolab.problem.micro import micro_g2_needs_charge
from evrptw_autolab.problem.physics import StopState
from evrptw_autolab.problem.types import EvaluationReport
from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.synthesis.contract import INSTANCE_API
from evrptw_autolab.synthesis.diagnostics import solution_diagnostic
from evrptw_autolab.synthesis.from_scratch import (
    NOOP_NOTE,
    PROPOSALS_PER_ROLE,
    STAGE_CANDIDATES,
    copy_run_provenance,
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
ROUTE_OK = (
    "def build_routes(instance):\n"
    "    depot = instance.depot_id\n"
    "    return [[depot, cid, depot] for cid in instance.customer_ids]\n\n"
    "def solve(instance, seed: int, time_limit_s: float):\n"
    "    return {'routes': build_routes(instance), 'metadata': {}}\n"
)


class Scripted:
    def __init__(self, handler) -> None:  # noqa: ANN001
        self.handler = handler
        self.prompts: list[tuple[str, str]] = []

    def complete(self, *, prompt: str, role: str, temperature: float, model: str, json_mode: bool = True) -> str:
        self.prompts.append((role, prompt))
        return self.handler(role, prompt, json_mode)


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


def test_g4_evaluates_all_four_instances(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    seen: list[str] = []

    def fake_run(solver_dir, instance, seed=0, limits=None):  # noqa: ANN001
        seen.append(instance.instance_id)
        # Earlier micro gates always pass; G4 panel has one battery failure.
        if not str(instance.instance_id).endswith("C5"):
            return EvaluationReport(
                parse_ok=True,
                feasible=True,
                vehicles=1,
                total_distance=1.0,
                first_fault={"family": "OK", "node_id": "", "route_index": -1, "detail": ""},
            )
        ok = instance.instance_id != "r104C5"
        return EvaluationReport(
            parse_ok=True,
            feasible=ok,
            vehicles=1 if ok else 0,
            total_distance=1.0 if ok else 0.0,
            routes=[["D0", "C1", "D0"]] if ok else [],
            first_fault={"family": "OK" if ok else "BATTERY", "node_id": "C1", "route_index": 0, "detail": "x"},
            battery_violations=0 if ok else 1,
        )

    class Inst:
        def __init__(self, instance_id: str) -> None:
            self.instance_id = instance_id

    monkeypatch.setattr("evrptw_autolab.synthesis.from_scratch.run_solver", fake_run)
    solver = tmp_path / "solver"
    solver.mkdir()
    (solver / "solver.py").write_text(ROUTE_OK, encoding="utf-8")
    panel = [Inst("c101C5"), Inst("c103C5"), Inst("r104C5"), Inst("r105C5")]  # type: ignore[list-item]
    result = evaluate_through(solver, "schneider_c5", limits=RunLimits(wall_clock_s=5), panel=panel)  # type: ignore[arg-type]
    c5_seen = [i for i in seen if str(i).endswith("C5")]
    assert c5_seen == ["c101C5", "c103C5", "r104C5", "r105C5"]
    assert result["ok"] is False
    assert result["instances_feasible"] == 3
    assert result["by_instance"]["r104C5"]["ok"] is False
    assert result["by_instance"]["c101C5"]["ok"] is True


def test_failed_candidates_never_overwrite_committed(tmp_path: Path) -> None:
    def handler(role: str, prompt: str, json_mode: bool = True) -> str:
        if role == "architect":
            return ARCHITECT
        if role == "critic":
            return CRITIC
        if '"stage": "executable"' in prompt and "missing_name_xyz" not in prompt:
            return EMPTY
        if "ops" in prompt or json_mode:
            return json.dumps(
                {
                    "hypothesis": "crash",
                    "ops": [
                        {
                            "action": "REPLACE",
                            "symbol": "solve",
                            "code": CRASH,
                        }
                    ],
                }
            )
        return CRASH

    backend = Scripted(handler)
    report = run_from_scratch(
        mode="five_agent",
        model="fake",
        backend=backend,
        workspace=tmp_path / "ws",
        max_llm_calls=16,
        stages=("executable", "routing"),
        proposals_per_role=1,
    )
    committed = (tmp_path / "ws" / "committed" / "solver.py").read_text(encoding="utf-8")
    assert "NameError" not in committed
    assert "def solve" in committed
    assert report["solver_hash"]
    assert PROPOSALS_PER_ROLE == 2
    assert STAGE_CANDIDATES["charging"] == ["charging", "search"]


def test_noop_note_is_defined() -> None:
    assert "already tested" in NOOP_NOTE


def test_single_agent_receives_runtime_diagnostics(tmp_path: Path) -> None:
    def handler(role: str, prompt: str, json_mode: bool = True) -> str:
        if role == "single" and "missing_name_xyz" not in prompt:
            return CRASH
        return EMPTY

    backend = Scripted(handler)
    run_from_scratch(
        mode="single_agent",
        model="fake",
        backend=backend,
        workspace=tmp_path / "single",
        max_llm_calls=4,
        stages=("executable",),
        proposals_per_role=1,
    )
    single_prompts = [prompt for role, prompt in backend.prompts if role == "single"]
    assert len(single_prompts) >= 2
    assert "NameError" in single_prompts[1]


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


def test_api_contract_lists_charging_representation() -> None:
    assert "ChargeDecision" in INSTANCE_API
    assert "station ID appears as a node" in INSTANCE_API


def test_battery_diagnostic_includes_route_and_states() -> None:
    instance = micro_g2_needs_charge()
    route = [instance.depot_id, instance.customer_ids[0], instance.depot_id]
    report = EvaluationReport(
        parse_ok=True,
        feasible=False,
        routes=[route],
        battery_violations=1,
        first_fault={
            "family": "BATTERY",
            "node_id": instance.depot_id,
            "route_index": 0,
            "detail": "battery_arrival=-20.000",
        },
    )
    diagnostic = solution_diagnostic(report, instance=instance)
    assert diagnostic["family"] == "BATTERY"
    assert diagnostic["route"] == route
    assert diagnostic["battery_deficit"] > 0
    assert diagnostic["states"]


def test_stopstate_is_frozen() -> None:
    stop = StopState(
        node_id="D0",
        arrival_time=0.0,
        service_start=0.0,
        departure_time=0.0,
        load=0.0,
        battery_arrival=10.0,
        battery_departure=10.0,
        energy_charged=0.0,
        distance_so_far=0.0,
    )
    try:
        stop.battery_departure = 99.0  # type: ignore[misc]
        raised = False
    except Exception:  # noqa: BLE001
        raised = True
    assert raised


def test_copy_run_provenance(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    (workspace / "committed").mkdir(parents=True)
    (workspace / "committed" / "solver.py").write_text(EMPTY, encoding="utf-8")
    (workspace / "rounds.jsonl").write_text("{}\n", encoding="utf-8")
    (workspace / "llm_calls.jsonl").write_text("{}\n", encoding="utf-8")
    dest = tmp_path / "raw" / "run"
    copy_run_provenance(workspace, dest, {"ok": True})
    assert (dest / "result.json").exists()
    assert (dest / "solver.py").exists()
