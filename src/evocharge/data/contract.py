"""Versioned dataset contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from evocharge.reproducibility import hash_mapping


class DatasetContract(BaseModel):
    dataset_name: str
    dataset_version: str
    source_doi: str | None = None
    instance_scale: int
    node_types: list[str]
    distance_representation: str
    travel_time_representation: str
    directed_arcs: bool
    distance_unit: str
    time_unit: str
    demand_unit: str
    energy_unit: str
    battery_capacity_source: str
    energy_consumption_model: str
    charging_model: str
    charging_policy: str
    station_revisit_policy: str
    fleet_policy: str
    objective_definition: str
    rounding_rules: dict[str, str] = Field(default_factory=dict)
    missing_or_ambiguous_fields: list[str] = Field(default_factory=list)
    evidence_files: list[str] = Field(default_factory=list)
    contract_hash: str = ""
    extras: dict[str, Any] = Field(default_factory=dict)

    def compute_hash(self) -> str:
        payload = self.model_dump()
        payload.pop("contract_hash", None)
        return hash_mapping(payload)

    def with_hash(self) -> DatasetContract:
        return self.model_copy(update={"contract_hash": self.compute_hash()})

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.model_dump(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def build_schneider_contract(
    *,
    evidence_files: list[str] | None = None,
    n_instances: int = 0,
    scales_observed: list[str] | None = None,
) -> DatasetContract:
    """Contract for Schneider Solomon E-VRPTW instances under dataset/schneider/."""
    ambiguities = [
        "Official Schneider paper charging policy assumed linear full recharge via g (inverse refuel rate).",
        "Filename tags (_21 vs C5/C10/C15) encode station/customer subsets; family is C/R/RC from Solomon id.",
    ]
    contract = DatasetContract(
        dataset_name="Schneider_E-VRPTW",
        dataset_version="v1.0",
        source_doi=None,
        instance_scale=n_instances,
        node_types=["depot", "customer", "station"],
        distance_representation="euclidean_coordinates",
        travel_time_representation="distance_over_velocity",
        directed_arcs=False,
        distance_unit="unspecified_coordinate_units",
        time_unit="minutes_solomon_style",
        demand_unit="unspecified",
        energy_unit="unspecified_fuel_units",
        battery_capacity_source="instance_param_Q",
        energy_consumption_model="linear_distance_times_r",
        charging_model="linear_provisional_g",
        charging_policy="provisional_full_recharge_at_stations",
        station_revisit_policy="unspecified_allow_multiple_pending_docs",
        fleet_policy="homogeneous_unlimited_copies_of_instance_vehicle",
        objective_definition=(
            "project_declared: lexicographic "
            "(infeasibility, unserved, vehicles, distance as primary_cost, "
            "travel_time, charging_time)"
        ),
        rounding_rules={"parser": "python_float", "comparisons": "abs_tol_1e-6"},
        missing_or_ambiguous_fields=ambiguities,
        evidence_files=evidence_files or ["dataset/schneider/raw_instances/"],
        extras={
            "status": "active",
            "placement": "dataset/schneider/raw_instances/",
            "converted_placement": "dataset/schneider/converted_instances/evrptw_instances/",
            "filename_pattern": "{c|r|rc}{id}(_21|C{5|10|15}).txt",
            "scales_observed": scales_observed
            or ["Cus_5", "Cus_10", "Cus_15", "Cus_100"],
            "primary_parser": "schneider_solomon_text",
            "vehicle_params": ["Q", "C", "r", "g", "v"],
            "node_type_codes": {"d": "depot", "c": "customer", "f": "station"},
            "split_protocol": "family_stratified_C_R_RC",
        },
    )
    return contract.with_hash()
