def solve(instance, seed: int, time_limit_s: float):
    import random
    random.seed(seed)
    
    # Initialize routes as empty lists for each vehicle
    routes = [[] for _ in range(len(instance.vehicles))]
    
    # Assign customers to vehicles based on their demand and capacity
    for customer in instance.customers:
        min_load = float('inf')
        best_vehicle = None
        
        for i, vehicle in enumerate(instance.vehicles):
            if (customer.demand + sum([node.demand for node in routes[i]])) <= vehicle.capacity:
                travel_time = travel_time(vehicle.depot, customer)
                energy_required = energy_required(vehicle.depot, customer, vehicle)
                
                if (travel_time + energy_required) < min_load and vehicle.battery >= energy_required:
                    min_load = travel_time + energy_required
                    best_vehicle = i
        
        # Assign the customer to the best vehicle
        routes[best_vehicle].append(customer)
    
    return {"routes": [list(map(lambda node: node.id, route)) for route in routes], "metadata": {}}