from evrptw_autolab.problem.physics import distance, energy_required, full_recharge, propagate_route

def greedy_charging(instance):
    routes = []
    for customer_id in instance.customer_ids:
        route = [instance.depot_id, customer_id, instance.depot_id]
        routes.append(route)
    return {"routes": routes, "metadata": {}}

def solve(instance, seed, time_limit_s):
    return greedy_charging(instance)