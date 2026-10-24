from pathlib import Path

from tests.conftest import DATA_ROOT

from evrptw_autolab.evaluation.fidelity import load_all, small_instances
from evrptw_autolab.problem.hashes import instance_hashes
from evrptw_autolab.problem.private import private_set, smoke_instance
from evrptw_autolab.problem.schneider import discover_instances


def test_private_set_hides_geometry(c101c5) -> None:
    small = small_instances(load_all(DATA_ROOT))
    hidden = private_set(small, seed=20260901, n=8)
    assert len(hidden) == 8
    assert all(item.instance_id.startswith("vfpriv_") for item in hidden)
    assert all(item.metadata.get("private") for item in hidden)
    original = {i.instance_id: i for i in small}
    moved = False
    for item in hidden:
        source = original[item.metadata["source_instance_id"]]
        if any(
            abs(a.x - b.x) > 1e-9 or abs(a.y - b.y) > 1e-9
            for a, b in zip(item.customers, source.customers, strict=True)
        ):
            moved = True
            break
    assert moved
    assert c101c5.instance_id not in {i.instance_id for i in hidden}


def test_smoke_instance_is_loadable() -> None:
    one = smoke_instance(1)
    two = smoke_instance(2)
    assert one.depot_id == "D0"
    assert one.customer_ids == ("C1",)
    assert two.customer_ids == ("C1", "C2")
    assert one.metadata.get("source_path")
    assert one.metadata.get("family") == "SMOKE"
    assert Path(one.metadata["source_path"]).exists()


def test_private_instance_hides_its_source_path(c101c5) -> None:
    from evrptw_autolab.problem.private import perturb_instance

    hidden = perturb_instance(c101c5, seed=7)
    assert hidden.metadata.get("source_path") is None
    assert hidden.customer_ids == c101c5.customer_ids


def test_instance_hashes_cover_ninety_two() -> None:
    hashes = instance_hashes(DATA_ROOT)
    assert len(hashes) == 92
    assert len(discover_instances(DATA_ROOT)) == 92
    assert all(len(value) == 64 for value in hashes.values())
