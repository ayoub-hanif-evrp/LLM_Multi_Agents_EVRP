import evrptw_autolab.problem.physics as physics

def solve(instance, seed, time_limit_s):
    # Initialize the routing mechanism
    routing = RoutingMechanism(instance)

    # Initialize the search engine
    search = SearchEngine(instance, routing)

    # Initialize the charging engine
    charging = ChargingEngine(instance, routing)

    # Initialize the critic engine
    critic = CriticEngine(instance, routing)

    # Run the search engine
    search.run(time_limit_s)

    # Run the charging engine
    charging.run(time_limit_s)

    # Run the critic engine
    critic.run(time_limit_s)

    # Return the final solution
    return search.solution