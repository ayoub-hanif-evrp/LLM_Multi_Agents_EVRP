# Qwen G4 mechanism analysis (MCB V1 seeds 11/22/33)

Analysis only — solvers are not modified.

Shared pattern across G4-reaching Qwen runs:

1. Build one-customer routes `[[depot, cid, depot] ...]`.
2. Detect battery insufficiency (often via `propagate_route`).
3. Insert a charging station — frequently applied to `routes[0]` only,
   or otherwise without fully general timing/energy handling across the Schneider panel.

Conceptual defect that repeats:

> local mechanism discovery succeeds; systematic algorithm generalization fails.

## Seed 11

- **path:** `C:\Users\AYOUB\OneDrive - EMSI\Bureau\PHD_WORK\LLM_Multi_Agents_EVRP\workspace\discovery_mcb_v1\qwen25_coder_7b\seed11\committed\solver.py`
- **G4_progress:** `3/4` stopped=`PARTIAL_G4_3`
- **primary:** `{'failure_class': 'FEASIBILITY', 'role': 'team', 'gate': 'G4', 'detail': 'BATTERY'}`
- **labels:** first-route-only, local-negative-battery-scan, one-customer-per-route-skeleton
- **generality:** charging/repair concentrated on routes[0]
- routes[0] refs=3 iterate_routes=False single_station_idx=False propagate=True

```python
: float):
    depot = instance.depot_id
    routes = [[depot, cid, depot] for cid in instance.customer_ids]
    
    metadata = {"seed": seed}
    
    # Check if the current route is battery-feasible
    states = propagate_route(instance, routes[0])
    if states[-1].battery_arrival < 0:
        # Find a charging station and insert it before the first customer
        available_station_ids = instance.station_ids
        for station_id in available_station_ids:
            new_route = [depot, station_id]
            new_route.extend(routes[0][1:])
            states = propagate_route(instance, new_route)
            if states[-1].battery_arr
```

## Seed 22

- **path:** `C:\Users\AYOUB\OneDrive - EMSI\Bureau\PHD_WORK\LLM_Multi_Agents_EVRP\workspace\discovery_mcb_v1\qwen25_coder_7b\seed22\committed\solver.py`
- **G4_progress:** `2/4` stopped=`PARTIAL_G4_2`
- **primary:** `{'failure_class': 'FEASIBILITY', 'role': 'team', 'gate': 'G4', 'detail': 'BATTERY'}`
- **labels:** first-route-only, local-negative-battery-scan, one-customer-per-route-skeleton
- **generality:** charging/repair concentrated on routes[0]
- routes[0] refs=14 iterate_routes=False single_station_idx=False propagate=True

```python
def solve(instance, seed: int, time_limit_s: float):
    depot = instance.depot_id
    routes = [[depot, cid, depot] for cid in instance.customer_ids]
    
    # Check if the route is battery-feasible
    states = propagate_route(instance, routes[0])
    if states[-1].battery_arrival < 0:
        # Find a charging station and insert it before the first customer
        available_stations = instance.station_ids
        for station_id in available_stations:
            for i in range(1, len(routes[0])):
                states = propagate_route(instance, [depot] + routes[0][:i] + [station_id] + routes[0][i:])
                if states[-1].batte
```

## Seed 33

- **path:** `C:\Users\AYOUB\OneDrive - EMSI\Bureau\PHD_WORK\LLM_Multi_Agents_EVRP\workspace\discovery_mcb_v1\qwen25_coder_7b\seed33\committed\solver.py`
- **G4_progress:** `3/4` stopped=`PARTIAL_G4_3`
- **primary:** `{'failure_class': 'FEASIBILITY', 'role': 'team', 'gate': 'G4', 'detail': 'BATTERY'}`
- **labels:** first-route-only, local-negative-battery-scan, one-customer-per-route-skeleton
- **generality:** charging/repair concentrated on routes[0]
- routes[0] refs=16 iterate_routes=False single_station_idx=False propagate=True

```python
: float):
    depot = instance.depot_id
    routes = [[depot, cid, depot] for cid in instance.customer_ids]
    
    metadata = {"seed": seed}
    
    # Check if the current route is battery-feasible
    states = propagate_route(instance, routes[0])
    if states[-1].battery_arrival < 0:
        # Find a charging station to place before each customer and at the depot
        for i in range(1, len(routes[0]) - 1):
            node_id = routes[0][i]
            available_stations = instance.station_ids
            for station in available_stations:
                new_route = routes[0][:i] + [station] + routes[0][i:]
                states =
```

## Conclusion

For the three Qwen runs that reached the real Schneider G4 panel, charging logic is
present but typically **not fully general** across all routes / families / timing
conditions. Remaining failures are dominated by **BATTERY** (and historically WINDOW
on r105C5 in related repair seeds). This supports the paper claim that small models
can synthesize local charging repairs while failing systematic generalization.
