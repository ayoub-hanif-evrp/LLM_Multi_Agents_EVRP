"""Load published Bezzi solution XML for validation only.

These files must never be used as construction hints or LLM feedback.

Published XML lists the node sequence and a route cost label, but not charge
amounts. Reconstruction of charge amounts for reference checks is done here
through the optimizer-side DP, then the trusted evaluator validates the
completed solution without inventing further decisions.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from evrptw_autolab.backbone.charge_completion import complete_solution_charges
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2


@dataclass(frozen=True, slots=True)
class PublishedBezziSolution:
    instance_name: str
    solution: SolutionV2
    route_costs: tuple[float, ...]
    charges_reconstructed: bool = False

    @property
    def total_cost(self) -> float:
        return float(sum(self.route_costs))


def load_published_bezzi_solution(
    path: Path | str,
    spec: ProblemSpecV2,
    *,
    reconstruct_charges: bool = True,
) -> PublishedBezziSolution:
    path = Path(path)
    root = ET.parse(path).getroot()
    routes: list[list[RouteStopV2]] = []
    costs: list[float] = []
    for route in root.findall("route"):
        cost_el = route.find("cost")
        if cost_el is None or cost_el.get("id") is None:
            raise ValueError(f"{path}: route missing <cost id=...>")
        costs.append(float(cost_el.get("id", "nan")))
        stops: list[RouteStopV2] = []
        for node_el in route.findall("node"):
            node_id = str(node_el.get("id"))
            node = spec.node_map.get(node_id)
            if node is None:
                raise ValueError(f"{path}: solution node {node_id} not in instance")
            event: Literal["visit", "pickup", "delivery", "charge", "depot"]
            if node.kind == "depot":
                event = "depot"
            elif node.kind == "station":
                event = "charge"
            else:
                event = "visit"
            stops.append(RouteStopV2(node_id, event=event))
        routes.append(stops)
    vehicle_id = spec.vehicle_types[0].type_id
    solution = SolutionV2(
        routes=routes,
        vehicle_assignments=[vehicle_id] * len(routes),
        metadata={"published_solution": str(path), "validation_only": True},
    )
    reconstructed = False
    if reconstruct_charges:
        solution = complete_solution_charges(spec, solution)
        reconstructed = True
        solution.metadata["published_solution"] = str(path)
        solution.metadata["validation_only"] = True
        solution.metadata["charges_reconstructed_via"] = "backbone.charge_completion"
    return PublishedBezziSolution(
        instance_name=str(root.get("instance") or path.stem),
        solution=solution,
        route_costs=tuple(costs),
        charges_reconstructed=reconstructed,
    )
