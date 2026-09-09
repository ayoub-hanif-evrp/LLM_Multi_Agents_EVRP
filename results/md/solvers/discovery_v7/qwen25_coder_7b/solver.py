def solve(instance, seed: int = 0, time_limit_s: float = 10.0):
    depot = instance.depot_id
    routes = [[depot, cid, depot] for cid in instance.customer_ids]
    return {
        "routes": routes,
        "metadata": {
            "seed": int(seed),
            "time_limit_s": float(time_limit_s),
            "lab_entry_recovery": True,
        },
    }
