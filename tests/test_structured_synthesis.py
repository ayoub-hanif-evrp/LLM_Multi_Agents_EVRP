"""Tests for Experiment B structured_synthesis (no paper/ writes)."""
from __future__ import annotations

import json
from pathlib import Path

from evrptw_autolab.evolution.evaluate import code_hash
from evrptw_autolab.llm.registry import (
    SKIPPED_NO_CREDENTIAL,
    FakeBackend,
    ModelProfile,
    availability,
    resolve_profile,
)
from evrptw_autolab.structured.archive import Population
from evrptw_autolab.structured.codegen import apply_function_to_solver, generate_function
from evrptw_autolab.structured.failure_memory import FailureMemory, FailureRecord
from evrptw_autolab.structured.fitness import fitness_key
from evrptw_autolab.structured.run import run_structured_synthesis
from evrptw_autolab.structured.signatures import (
    REQUIRED_FUNCTIONS,
    assemble_solver_source,
)
from evrptw_autolab.structured.spec import default_spec, validate_spec

CONSTRUCT = '''\
def construct(instance, rng):
    depot = instance.depot_id
    return [[depot, cid, depot] for cid in instance.customer_ids]
'''

REPAIR = '''\
def repair(instance, routes, rng):
    return [list(route) for route in routes]
'''

IMPROVE = '''\
def improve(instance, routes, rng):
    return [list(route) for route in routes]
'''

SOLVE = '''\
def solve(instance, seed: int, time_limit_s: float):
    import random
    rng = random.Random(int(seed))
    routes = construct(instance, rng)
    routes = repair(instance, routes, rng)
    routes = improve(instance, routes, rng)
    return {"routes": routes, "metadata": {"seed": int(seed)}}
'''

ARCHITECT = json.dumps(default_spec().model_dump())


def _fn_json(name: str, code: str) -> str:
    return json.dumps({"function": name, "code": code})


def test_assemble_solver_source_has_all_four_defs() -> None:
    source = assemble_solver_source(None, CONSTRUCT, REPAIR, IMPROVE, SOLVE)
    for name in REQUIRED_FUNCTIONS:
        assert f"def {name}" in source
    compile(source, "<solver.py>", "exec")


def test_fitness_ordering_prefers_higher_g4() -> None:
    low = fitness_key({"gates_passed": 4, "instances_feasible": 1, "diagnostic": {}})
    high = fitness_key({"gates_passed": 4, "instances_feasible": 3, "diagnostic": {}})
    assert high > low
    better_gates = fitness_key({"gates_passed": 3, "instances_feasible": 0, "diagnostic": {}})
    worse_gates = fitness_key({"gates_passed": 2, "instances_feasible": 4, "diagnostic": {}})
    assert better_gates > worse_gates


def test_failure_memory_cap_and_relevant() -> None:
    mem = FailureMemory()
    for i in range(25):
        mem.add(
            FailureRecord(
                code_hash=f"h{i}",
                function_changed="repair",
                failure_family="BATTERY" if i % 2 == 0 else "VISIT",
                failed_instance=f"C{i}",
                diagnostic=f"battery_deficit={i}" if i % 2 == 0 else f"missing C{i}",
                attempted_repair="insert station",
                effect="unchanged",
            )
        )
    assert len(mem.records) == 20
    hits = mem.relevant("BATTERY battery_deficit on route", k=3)
    assert len(hits) <= 3
    assert any(r.failure_family == "BATTERY" for r in hits)


def test_archive_rejects_duplicate_hashes() -> None:
    pop = Population(archive_size=8)
    src = assemble_solver_source(None, CONSTRUCT, REPAIR, IMPROVE, SOLVE)
    info = {"gates_passed": 1, "instances_feasible": 0, "diagnostic": {}}
    assert pop.add(src, info, generation=0) is True
    assert pop.add(src, info, generation=1) is False
    assert len(pop) == 1
    # Distinct content accepted.
    other = src + "\n# tweak\n"
    assert pop.add(other, info, generation=2) is True
    assert len(pop) == 2
    assert code_hash(src) != code_hash(other)


def test_fake_backend_generates_one_function_and_assembles() -> None:
    backend = FakeBackend({"construct": [_fn_json("construct", CONSTRUCT)]})
    name, code, err = generate_function(
        backend,
        function_name="construct",
        model="fake",
        spec=default_spec(),
    )
    assert err == ""
    assert name == "construct"
    assert "def construct" in code
    parent = assemble_solver_source(None, CONSTRUCT, REPAIR, IMPROVE, SOLVE)
    # Replace improve with a tiny variant.
    improve2 = IMPROVE.replace("list(route)", "list(route)[:]")
    new_src, apply_err = apply_function_to_solver(parent, "improve", improve2)
    assert apply_err == ""
    assert "def improve" in new_src
    assert "def solve" in new_src


def test_run_fake_backend_reaches_executable(tmp_path: Path) -> None:
    paper_before = list(Path("results/paper").rglob("*") if Path("results/paper").exists() else [])
    replies = {
        "architect": [ARCHITECT],
        "construct": [_fn_json("construct", CONSTRUCT)],
        "repair": [_fn_json("repair", REPAIR)],
        "improve": [_fn_json("improve", IMPROVE)],
        "solve": [_fn_json("solve", SOLVE)],
        "mutate": [_fn_json("repair", REPAIR)],
        "crossover": [_fn_json("improve", IMPROVE)],
        "error_analyst": [
            json.dumps(
                {
                    "family": "VISIT",
                    "function_to_change": "repair",
                    "hypothesis": "noop",
                    "evidence": [],
                }
            )
        ],
        "repair_coder": [_fn_json("repair", REPAIR)],
        "judge": [json.dumps({"decision": "reject", "reason": "noop"})],
    }
    backend = FakeBackend(replies)
    workspace = tmp_path / "structured_ws"
    report = run_structured_synthesis(
        model="fake",
        backend=backend,
        workspace=workspace,
        max_llm_calls=40,
        token_ceiling=None,
        max_generations=1,
        archive_size=4,
        offspring_per_generation=2,
        seed=11,
        ablation="full",
        repo_root=Path(".").resolve(),
    )
    assert report["experiment"] == "structured_synthesis"
    assert report["executable"] is True
    solver = workspace / "committed" / "solver.py"
    assert solver.exists()
    text = solver.read_text(encoding="utf-8")
    assert "def solve" in text
    # Zero LLM imports in final solver.
    assert "evrptw_autolab.llm" not in text
    assert "openai" not in text.lower()
    paper_after = list(Path("results/paper").rglob("*") if Path("results/paper").exists() else [])
    assert paper_before == paper_after
    assert "results/paper" not in str(report.get("solver_path") or "")


def test_default_spec_validates() -> None:
    assert validate_spec(default_spec()) == []


def test_openai_compatible_credential_availability(monkeypatch) -> None:  # noqa: ANN001
    profile = ModelProfile(
        id="x",
        provider="openai_compatible",
        model="deepseek-v4-pro",
        api_key_env="DEEPSEEK_API_KEY_TEST_STRUCTURED",
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY_TEST_STRUCTURED", raising=False)
    assert availability(profile) == SKIPPED_NO_CREDENTIAL
    monkeypatch.setenv("DEEPSEEK_API_KEY_TEST_STRUCTURED", "sk-test")
    assert availability(profile) == "installed"


def test_new_model_profiles_present() -> None:
    for pid in (
        "deepseek_v4_pro",
        "gpt6_sol",
        "claude_opus_55",
        "claude_sonnet_55",
        "qwen3_coder_480b_hosted",
    ):
        profile = resolve_profile(pid)
        assert profile.provider == "openai_compatible"
        assert profile.enabled is True
        assert profile.api_key_env
