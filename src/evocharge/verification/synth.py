"""Tiny synthetic instances for verification (no tests/ dependency)."""

from __future__ import annotations

from evocharge.domain.instance import Instance
from evocharge.domain.node import Node
from evocharge.domain.vehicle import Vehicle


def make_tiny_instance() -> Instance:
    nodes = {
        "D0": Node("D0", "depot", (0.0, 0.0), due_time=100.0),
        "S0": Node("S0", "station", (0.0, 0.0), due_time=100.0),
        "S1": Node("S1", "station", (5.0, 0.0), due_time=100.0),
        "C0": Node(
            "C0",
            "customer",
            (1.0, 0.0),
            demand=1.0,
            service_duration=1.0,
            ready_time=0.0,
            due_time=50.0,
        ),
        "C1": Node(
            "C1",
            "customer",
            (2.0, 0.0),
            demand=1.0,
            service_duration=1.0,
            ready_time=0.0,
            due_time=50.0,
        ),
    }
    vehicle = Vehicle(
        freight_capacity=10.0,
        battery_capacity=100.0,
        initial_soc=100.0,
        consumption_rate=1.0,
        velocity=1.0,
        inverse_refuel_rate=0.1,
        charging_speed=10.0,
    )
    return Instance(
        instance_id="synth_tiny_m7",
        dataset_name="synthetic",
        nodes=nodes,
        depot_id="D0",
        customer_ids=("C0", "C1"),
        station_ids=("S0", "S1"),
        vehicle=vehicle,
        horizon=100.0,
        metadata={"family_key": "SYN_wide"},
    )
