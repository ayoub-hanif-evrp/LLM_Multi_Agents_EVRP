"""Contract and instance validation helpers."""

from __future__ import annotations

import json
from pathlib import Path

from evocharge.data.contract import DatasetContract
from evocharge.domain.instance import Instance


def validate_contract_file(path: Path) -> DatasetContract:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    contract = DatasetContract.model_validate(raw)
    expected = contract.compute_hash()
    if contract.contract_hash and contract.contract_hash != expected:
        raise ValueError(
            f"Contract hash mismatch: stored={contract.contract_hash} computed={expected}"
        )
    return contract


def validate_instance_basic(instance: Instance) -> list[str]:
    errors: list[str] = []
    if instance.depot_id not in instance.nodes:
        errors.append("depot_missing")
    if instance.nodes[instance.depot_id].kind != "depot":
        errors.append("depot_kind")
    if not instance.customer_ids:
        errors.append("no_customers")
    if instance.vehicle.battery_capacity <= 0:
        errors.append("nonpositive_battery")
    if instance.vehicle.freight_capacity <= 0:
        errors.append("nonpositive_capacity")
    if instance.vehicle.velocity <= 0:
        errors.append("nonpositive_velocity")
    return errors
