from tests.conftest import DATA_ROOT

from evrptw_autolab.evaluation.fidelity import (
    CONFIRMATION_FAMILIES,
    DISCOVERY_FAMILIES,
    family_representatives,
    load_all,
    partition_of,
    small_instances,
    split_instances,
    write_split_manifest,
)
from evrptw_autolab.evaluation.literature import SCHNEIDER_2014_SMALL_CPLEX
from evrptw_autolab.evaluation.runner import instances_for_fidelity


def test_three_way_split() -> None:
    split = split_instances(load_all(DATA_ROOT))
    assert all(i.metadata["family"] in DISCOVERY_FAMILIES for i in split["discovery"])
    assert all(i.metadata["family"] in CONFIRMATION_FAMILIES for i in split["confirmation"])
    assert all(i.metadata["family"] == "RC2" for i in split["heldout"])
    assert partition_of(next(i for i in split["discovery"] if i.instance_id == "c101C5")) == "discovery"
    assert partition_of(next(i for i in split["confirmation"] if i.instance_id == "c206C5")) == "confirmation"
    ids = {i.instance_id for i in split["discovery"]}
    assert "c101C5" in ids
    assert "c206C5" not in ids
    assert "rc204C5" not in ids
    assert len(split["discovery"]) + len(split["confirmation"]) + len(split["heldout"]) == 92


def test_thirty_six_small_instances() -> None:
    small = small_instances(load_all(DATA_ROOT))
    assert len(small) == 36
    split = split_instances(small)
    assert len(split["discovery"]) == 12
    assert len(split["confirmation"]) == 18
    assert len(split["heldout"]) == 6
    assert set(SCHNEIDER_2014_SMALL_CPLEX) == {i.instance_id for i in small}


def test_fidelity_selection_excludes_heldout() -> None:
    discovery = split_instances(load_all(DATA_ROOT))["discovery"]
    for level in ("F1", "F2", "F3"):
        chosen = instances_for_fidelity(discovery, level)
        assert chosen
        assert all(i.metadata["family"] != "RC2" for i in chosen)
        assert all(partition_of(i) == "discovery" for i in chosen)
    large = family_representatives(discovery, large=True)
    assert all(i.metadata["scale"] == "large" for i in large)


def test_split_manifest(tmp_path) -> None:
    split = split_instances(load_all(DATA_ROOT))
    path = write_split_manifest(tmp_path / "split.json", split)
    text = path.read_text(encoding="utf-8")
    assert "RC2" in text
    assert "c101C5" in text
    assert "confirmation_ids" in text
