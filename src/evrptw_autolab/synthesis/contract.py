"""Problem/solver contract injected into every agent payload. Not a solver."""

FAULT_ATLAS = {
    "families": ["VISIT", "DEPOT", "CAPACITY", "WINDOW", "BATTERY", "CHARGE_POLICY"],
    "owners": {
        "VISIT": "routing",
        "DEPOT": "routing",
        "CAPACITY": "routing",
        "WINDOW": "charging",
        "BATTERY": "charging",
        "CHARGE_POLICY": "charging",
        "CRASH": "search",
        "PARSE": "search",
        "OK": "search",
    },
    "lex_objective": ["feasibility", "vehicles", "distance"],
    "lab_ranking": (
        "The laboratory ranks complete solve() outputs lexicographically: "
        "no-crash, then feasibility, then fewer vehicles, then smaller distance. "
        "A non-crashing infeasible solver beats a crashing one. "
        "Your solver may use any internal search or acceptance rule."
    ),
}

INSTANCE_API = """
instance is evrptw_autolab.problem.types.EVRPTWInstance.
Node ids are strings (e.g. depot 'D0', customer 'C30'). Never use integer 0 as the depot.

instance.depot_id            # str
instance.customer_ids        # tuple[str, ...]
instance.n_customers         # int == len(customer_ids)
instance.station_ids         # tuple[str, ...]
instance.customers           # tuple[Node, ...]  — NOT a dict; use [c.id for c in instance.customers]
instance.stations            # tuple[Node, ...]
instance.depot               # Node
instance.node_map[node_id]   # Node
instance.vehicle             # ONE VehicleSpec — there is NO vehicle_map
instance.vehicle.capacity, .battery_capacity, .consumption_rate, .velocity, .inverse_refuel_rate, .start_soc

Do NOT redefine class EVRPTWInstance / Node / StopState. Do NOT invent attributes.
Common crash fixes:
- AttributeError n_customers → use instance.n_customers or len(instance.customer_ids)
- customers.keys() → customers is a tuple of Node; iterate instance.customer_ids
- vehicle_map → use instance.vehicle
- distance(id,id) → distance(instance.node_map[a], instance.node_map[b])

Routes must be list[list[str]], each starting and ending at instance.depot_id.
The depot id may appear only as the first and last stop. D → C1 → D → C2 → D is invalid:
an internal depot must not make several trips count as one vehicle.

Physics signatures (positional Node / VehicleSpec — do not pass floats or routes):
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route
distance(a: Node, b: Node) -> float
travel_time(a: Node, b: Node, vehicle) -> float
energy_required(a: Node, b: Node, vehicle) -> float
full_recharge(vehicle, battery_on_arrival: float)  # function, not a package
propagate_route(instance, node_ids: list[str]) -> list[StopState]
StopState has battery_arrival, service_start, load, arrival_time.
Get a Node with instance.node_map[node_id]. instance.customers is a tuple of Node; do not index it with a Node or dict.
A route stores STRING ids only.
Every customer_id must appear exactly once across routes.
`def solve` must be a **module-level function** in solver.py, not a class method.
Do not `from random import seed` while the argument is also named `seed`. Use `import random` then `random.seed(seed)`.

You may test a candidate with the lab oracle (not a construction heuristic):
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.types import CandidateSolution
packet = first_fault(instance, CandidateSolution(routes=routes))
# packet["family"] == "OK" means the oracle accepts the routes.

The lab reports a first-fault packet (family, node_id, route_index, detail). Fix that family.

def solve(instance, seed: int, time_limit_s: float) must live in solver.py and return
{"routes": [...], "metadata": {...}} or an object with .routes.
No LLM calls. Do not import evrptw_autolab.evaluation or evrptw_autolab.experiments.
Do not hard-code instance ids, BKS tables, or routes.
"""


PROBLEM_BRIEF = """
EVRPTW (Schneider 2014, 92-instance contract): visit each customer once.
Respect capacity, time windows, and battery. Stations use full recharge only (no partial recharge).
Unlimited fleet. Laboratory ranking of a finished solve() is lexicographic:
feasibility, then number of vehicles, then total Euclidean distance.
Invent the algorithm yourself.
The framework does not supply construction, charging-repair, merge, or acceptance operators.
""" + INSTANCE_API

API_SNIPPET = INSTANCE_API
