from evrptw_autolab.problem.micro import micro_g1_one_customer, micro_g2_needs_charge, micro_g3_two_customers
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution


def test_micro_gates_physics() -> None:
    g1 = micro_g1_one_customer()
    d, c = g1.depot_id, g1.customer_ids[0]
    assert first_fault(g1, CandidateSolution([[d, c, d]]))["family"] == "OK"

    g2 = micro_g2_needs_charge()
    d, c, s = g2.depot_id, g2.customer_ids[0], g2.station_ids[0]
    assert first_fault(g2, CandidateSolution([[d, c, d]]))["family"] == "BATTERY"
    assert first_fault(g2, CandidateSolution([[d, s, c, d]]))["family"] == "OK"

    g3 = micro_g3_two_customers()
    d = g3.depot_id
    routes = [[d, cid, d] for cid in g3.customer_ids]
    assert first_fault(g3, CandidateSolution(routes))["family"] == "OK"


def test_p1_has_no_recovery_import() -> None:
    from pathlib import Path

    text = Path(__file__).resolve().parents[1].joinpath(
        "src/evrptw_autolab/build/p1_minimal.py"
    ).read_text(encoding="utf-8")
    assert "force_executable_entry" not in text
    assert "entry_recovery" not in text
    assert "EXECUTABLE_ENTRY" not in text
