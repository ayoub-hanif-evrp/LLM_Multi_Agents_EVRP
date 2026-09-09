from evrptw_autolab.agents import FIXED_ROLES, ArchitectPlan, build_team
from evrptw_autolab.llm.registry import FakeBackend
from evrptw_autolab.orchestration.activation import roles_for_plan


def test_exactly_five_fixed_roles() -> None:
    assert FIXED_ROLES == ("architect", "routing", "charging", "search", "critic")
    backend = FakeBackend(
        {
            "architect": "{}",
            "routing": "{}",
            "charging": "{}",
            "search": "{}",
            "critic": "{}",
        }
    )
    team = build_team(backend, model="fake")
    assert set(team) == set(FIXED_ROLES)


def test_gated_activation_does_not_change_team_size() -> None:
    plan = ArchitectPlan(
        hypothesis="charging",
        target="CHARGING",
        evidence=[],
        agents_to_activate=["charging"],
        files_or_components=["charging.py"],
        success_criteria=["feasibility"],
    )
    active = roles_for_plan(plan)
    assert "architect" in active and "charging" in active and "critic" in active
    assert "search" in active
    assert "routing" not in active
def test_charging_gate_also_activates_search() -> None:
    from evrptw_autolab.orchestration.activation import ensure_integration

    assert "search" in ensure_integration(["architect", "charging", "critic"])
