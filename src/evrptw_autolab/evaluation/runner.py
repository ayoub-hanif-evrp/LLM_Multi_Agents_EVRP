"""Select Schneider instances for a fidelity level. Generated-solver execution was archived."""

from __future__ import annotations

from evrptw_autolab.evaluation.fidelity import (
    HELDOUT_FAMILY,
    by_customer_count,
    family_representatives,
    partition_of,
)
from evrptw_autolab.problem.types import EVRPTWInstance


def instances_for_fidelity(
    discovery: list[EVRPTWInstance],
    level: str,
    *,
    max_instances: int | None = None,
) -> list[EVRPTWInstance]:
    if level == "F1":
        chosen = by_customer_count(discovery, [5])
    elif level == "F2":
        chosen = by_customer_count(discovery, [5, 10, 15])
    elif level in {"F3", "F4"}:
        chosen = family_representatives(discovery, large=True)
        if level == "F4":
            chosen = chosen + by_customer_count(discovery, [15])
    else:
        raise ValueError(f"unknown fidelity {level}")
    leaked = any(
        partition_of(instance) == "heldout" or str(instance.metadata.get("family")) == HELDOUT_FAMILY
        for instance in chosen
    )
    if leaked:
        raise RuntimeError("held-out family leaked into fidelity selection")
    if max_instances is not None:
        chosen = chosen[:max_instances]
    return chosen
