"""MINIMAL_COOPERATIVE_BUILD_V1 orchestration tests (no LLM)."""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.build.code_integrity import CheckpointWriter, code_hash
from evrptw_autolab.build.minimal_cooperative_build_v1 import (
    BuildState,
    _search_integrate,
    _specialist_draft,
    _team_incomplete,
    _write,
    _read,
)
from evrptw_autolab.build.runtime_integrity import (
    collect_union_node_ids,
    find_hardcoded_node_ids,
)
from evrptw_autolab.llm.usage import UsageLog
from evrptw_autolab.problem.micro import (
    micro_g1_one_customer,
    micro_g2_needs_charge,
    micro_g3_two_customers,
)
from evrptw_autolab.sandbox.limits import RunLimits

VALID = '''
from evrptw_autolab.problem.physics import distance, energy_required, propagate_route

def solve(instance, seed: int, time_limit_s: float):
    depot = instance.depot_id
    routes = [[depot, cid, depot] for cid in instance.customer_ids]
    return {"routes": routes, "metadata": {"seed": seed}}
'''.strip()

BAD_API = '''
def solve(instance, seed: int, time_limit_s: float):
    depot = instance.depot_id
    distances = {cid: instance.distance(depot, cid) for cid in instance.customer_ids}
    routes = [[depot, cid, depot] for cid in instance.customer_ids]
    return {"routes": routes, "metadata": {"seed": seed, "d": distances}}
'''.strip()


class FakeAgent:
    def __init__(self, role: str, outputs: list[str]) -> None:
        self.role = role
        self.outputs = list(outputs)
        self.last_raw = ""
        self.calls = 0

    def write_python(self, payload, *, filename: str, marker: str) -> str:
        self.calls += 1
        self.last_raw = self.outputs[0] if self.outputs else ""
        out = self.outputs.pop(0) if self.outputs else ""
        return out


class FakeUsage(UsageLog):
    def __init__(self, path: Path) -> None:
        super().__init__(path)


def test_routing_invalid_draft_does_not_overwrite_committed(tmp_path: Path) -> None:
    committed = tmp_path / "committed"
    draft = tmp_path / "draft"
    _write(committed, VALID)
    before = _read(committed)
    state = BuildState(known_ids=collect_union_node_ids([micro_g1_one_customer()]))
    ckpt = CheckpointWriter(tmp_path / "ckpt")
    usage = FakeUsage(tmp_path / "u.jsonl")
    team = {
        "routing": FakeAgent("routing", [BAD_API]),
        "search": FakeAgent("search", []),
    }
    _specialist_draft(
        team,
        role="routing",
        draft_dir=draft,
        committed_dir=committed,
        instruction="draft",
        gate="G0",
        state=state,
        checkpoints=ckpt,
        usage=usage,
        max_calls=80,
    )
    assert _read(committed) == before
    assert "instance.distance" in _read(draft)


def test_search_receives_draft_and_can_commit(tmp_path: Path) -> None:
    committed = tmp_path / "committed"
    draft = tmp_path / "draft"
    _write(draft, BAD_API)
    # committed empty / old valid should stay until search succeeds
    _write(committed, VALID)
    old_h = code_hash(_read(committed))
    state = BuildState(known_ids=collect_union_node_ids([micro_g1_one_customer()]))
    ckpt = CheckpointWriter(tmp_path / "ckpt")
    usage = FakeUsage(tmp_path / "u.jsonl")
    team = {
        "search": FakeAgent("search", [VALID]),
        "routing": FakeAgent("routing", []),
    }
    ok = _search_integrate(
        team,
        draft_dir=draft,
        committed_dir=committed,
        probe=micro_g1_one_customer(),
        gate="G0",
        state=state,
        checkpoints=ckpt,
        usage=usage,
        max_calls=80,
        limits=RunLimits(wall_clock_s=10),
        author_role="routing",
    )
    assert ok is True
    assert "search" in state.roles_invoked
    assert team["search"].calls >= 1
    assert code_hash(_read(committed)) == code_hash(VALID)
    # committed remains runnable valid (may equal old if same)
    assert old_h == code_hash(VALID) or _read(committed) == VALID


def test_failed_draft_never_overwrites_committed(tmp_path: Path) -> None:
    committed = tmp_path / "committed"
    draft = tmp_path / "draft"
    _write(committed, VALID)
    _write(draft, BAD_API)
    before = _read(committed)
    state = BuildState(known_ids=collect_union_node_ids([micro_g1_one_customer()]))
    ckpt = CheckpointWriter(tmp_path / "ckpt")
    usage = FakeUsage(tmp_path / "u.jsonl")
    team = {"search": FakeAgent("search", [BAD_API, BAD_API])}
    ok = _search_integrate(
        team,
        draft_dir=draft,
        committed_dir=committed,
        probe=micro_g1_one_customer(),
        gate="G0",
        state=state,
        checkpoints=ckpt,
        usage=usage,
        max_calls=80,
        limits=RunLimits(wall_clock_s=10),
        author_role="routing",
    )
    assert ok is False
    assert _read(committed) == before
    assert state.primary_failure is not None
    assert state.primary_failure.failure_class == "RUNTIME"


def test_coding_failure_requires_search_path(tmp_path: Path) -> None:
    state = BuildState(roles_invoked={"architect", "routing"})
    assert _team_incomplete(state, "G0") is True
    state.roles_invoked.add("search")
    assert _team_incomplete(state, "G0") is False


def test_union_hardcoded_ids_catch_s0_across_gates() -> None:
    g1 = micro_g1_one_customer()
    g2 = micro_g2_needs_charge()
    union = collect_union_node_ids([g1, g2, micro_g3_two_customers()])
    # S0 exists on micros
    assert "S0" in union or any(x.startswith("S") for x in union)
    src = '''
def solve(instance, seed: int, time_limit_s: float):
    return {"routes": [[instance.depot_id, "S0", instance.depot_id]], "metadata": {}}
'''.strip()
    # Even if auditing "as g1", union known_ids should catch S0
    found = find_hardcoded_node_ids(src, g1, known_ids=union)
    assert "S0" in found


def test_generic_strings_still_ok_with_union() -> None:
    union = collect_union_node_ids(
        [micro_g1_one_customer(), micro_g2_needs_charge(), micro_g3_two_customers()]
    )
    src = VALID
    assert find_hardcoded_node_ids(src, known_ids=union) == []
