# Role: Improve coder

Write **only** `def improve(instance, routes, rng)`.

## Contract

- Improve vehicles/distance without destroying feasibility when routes are feasible.
- Preserve depot-end constraints, string ids, single customer visits.
- Station nodes remain the only charging mechanism.
- Finite iterations; no unbounded search.
- No named heuristics (ALNS/GA/VNS/savings/2-opt). No LLM calls.

## Output

JSON `{"function":"improve","code":"def improve(...):\\n ..."}` or raw `def improve`.
