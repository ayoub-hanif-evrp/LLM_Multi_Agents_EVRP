import random
from evrptw_autolab.problem.types import EVRPTWInstance, Node, VehicleSpec, CandidateSolution
from evrptw_autolab.problem.physics import distance, travel_time, energy_required, full_recharge, propagate_route

def solve(instance: EVRPTWInstance, seed: int, time_limit_s: float) -> dict:
    random.seed(seed)
    
    depot_id = instance.depot_id
    customer_ids = instance.customer_ids
    station_ids = instance.station_ids
    customers = instance.customers
    stations = instance.stations
    vehicle = instance.vehicle
    
    def insert_charge(route: list[str]) -> list[str]:
        new_route = [depot_id]
        current_battery = vehicle.start_soc
        for i, node_id in enumerate(route):
            if i > 0 and instance.node_map[node_id].kind == 'station':
                charge_decision = full_recharge(vehicle, current_battery)
                new_route.append(node_id)
                current_battery = charge_decision.battery_departure
            else:
                new_route.append(node_id)
                current_battery -= travel_time(instance.node_map[route[i-1]], instance.node_map[node_id], vehicle) * vehicle.consumption_rate
        new_route.append(depot_id)
        return new_route
    
    def build_routes(customers: tuple[Node, ...], stations: tuple[Node, ...], vehicle: VehicleSpec) -> list[list[str]]:
        routes = []
        remaining_customers = list(customers)
        while remaining_customers:
            route = [depot_id]
            current_battery = vehicle.start_soc
            while remaining_customers:
                next_customer = min(remaining_customers, key=lambda c: travel_time(instance.depot, c, vehicle) * vehicle.consumption_rate)
                if current_battery < travel_time(instance.depot, next_customer, vehicle) * vehicle.consumption_rate:
                    break
                route.append(next_customer.id)
                remaining_customers.remove(next_customer)
                current_battery -= travel_time(instance.depot, next_customer, vehicle) * vehicle.consumption_rate
            route = insert_charge(route)
            routes.append(route)
        return routes
    
    routes = build_routes(customers, stations, vehicle)
    return {"routes": routes, "metadata": {}}