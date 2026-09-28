# solver.py

import random
from typing import List, Dict

class Problem:
    def __init__(self):
        self.depot_id = 0
        self.customer_ids = [1, 2, 3, 4]
        self.customers = [
            {"id": 1, "location": (0, 0)},
            {"id": 2, "location": (1, 1)},
            {"id": 3, "location": (2, 2)},
            {"id": 4, "location": (3, 3)}
        ]

    def distance(self, node1: int, node2: int) -> float:
        return ((self.customers[node1]["location"][0] - self.customers[node2]["location"][0])**2 + 
                (self.customers[node1]["location"][1] - self.customers[node2]["location"][1])**2)**0.5

    def travel_time(self, node1: int, node2: int) -> float:
        return 1 / self.distance(node1, node2)

    def energy_required(self, node: int) -> float:
        return 10 * self.distance(node, self.depot_id)

    def full_recharge(self, node: int) -> bool:
        return random.random() < 0.5

def solve(instance: Problem, seed: int, time_limit_s: float) -> Dict[str, List[int]]:
    # Implement the search algorithm here
    routes = []
    for _ in range(10):  # Example of a simple greedy approach
        route = [instance.depot_id]
        while len(route) < len(instance.customer_ids):
            next_node = random.choice([node for node in instance.customer_ids if node not in route])
            route.append(next_node)
        routes.append(route)
    return {"routes": routes, "metadata": {}}