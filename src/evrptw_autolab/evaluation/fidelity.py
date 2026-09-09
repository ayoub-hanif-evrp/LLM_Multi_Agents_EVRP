"""Deterministic discovery / confirmation / held-out splits. RC2 never enters discovery."""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.problem.schneider import discover_instances, load_instance
from evrptw_autolab.problem.types import EVRPTWInstance

ROOT = Path(__file__).resolve().parents[3]

DISCOVERY_FAMILIES = frozenset({"C1", "R1"})
CONFIRMATION_FAMILIES = frozenset({"C2", "R2", "RC1"})
HELDOUT_FAMILY = "RC2"
SMALL_CUSTOMER_COUNTS = (5, 10, 15)


def load_all(data_root: Path | None = None) -> list[EVRPTWInstance]:
    root = data_root or (ROOT / "dataset" / "schneider" / "raw_instances")
    return [load_instance(path) for path in discover_instances(root)]


def partition_of(instance: EVRPTWInstance) -> str:
    family = str(instance.metadata.get("family"))
    if family in DISCOVERY_FAMILIES:
        return "discovery"
    if family in CONFIRMATION_FAMILIES:
        return "confirmation"
    if family == HELDOUT_FAMILY:
        return "heldout"
    raise ValueError(f"unknown family {family!r} for {instance.instance_id}")


def split_instances(
    instances: list[EVRPTWInstance], *, held_out_family: str = HELDOUT_FAMILY
) -> dict[str, list[EVRPTWInstance]]:
    if held_out_family != HELDOUT_FAMILY:
        raise ValueError(f"held-out family is frozen as {HELDOUT_FAMILY}")
    discovery = [i for i in instances if partition_of(i) == "discovery"]
    confirmation = [i for i in instances if partition_of(i) == "confirmation"]
    heldout = [i for i in instances if partition_of(i) == "heldout"]
    if any(str(i.metadata.get("family")) == held_out_family for i in discovery + confirmation):
        raise RuntimeError("held-out family leaked into development partitions")
    if any(str(i.metadata.get("family")) in CONFIRMATION_FAMILIES for i in discovery):
        raise RuntimeError("confirmation family leaked into discovery")
    return {"discovery": discovery, "confirmation": confirmation, "heldout": heldout}


def by_customer_count(instances: list[EVRPTWInstance], sizes: list[int]) -> list[EVRPTWInstance]:
    wanted = set(sizes)
    selected = [i for i in instances if len(i.customer_ids) in wanted]
    selected.sort(key=lambda i: i.instance_id)
    return selected


def small_instances(instances: list[EVRPTWInstance]) -> list[EVRPTWInstance]:
    return by_customer_count(instances, list(SMALL_CUSTOMER_COUNTS))


def family_representatives(instances: list[EVRPTWInstance], *, large: bool) -> list[EVRPTWInstance]:
    chosen: dict[str, EVRPTWInstance] = {}
    for instance in sorted(instances, key=lambda i: i.instance_id):
        family = str(instance.metadata.get("family"))
        is_large = instance.metadata.get("scale") == "large"
        if is_large != large or family in chosen:
            continue
        chosen[family] = instance
    return [chosen[k] for k in sorted(chosen)]


def write_split_manifest(
    path: Path, split: dict[str, list[EVRPTWInstance]], *, held_out_family: str = HELDOUT_FAMILY
) -> Path:
    import json

    payload = {
        "contract": "schneider_92_full_recharge",
        "held_out_family": held_out_family,
        "discovery_families": sorted(DISCOVERY_FAMILIES),
        "confirmation_families": sorted(CONFIRMATION_FAMILIES),
        "discovery_ids": [instance.instance_id for instance in split["discovery"]],
        "confirmation_ids": [instance.instance_id for instance in split.get("confirmation", [])],
        "heldout_ids": [instance.instance_id for instance in split["heldout"]],
        "n_discovery": len(split["discovery"]),
        "n_confirmation": len(split.get("confirmation", [])),
        "n_heldout": len(split["heldout"]),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path
