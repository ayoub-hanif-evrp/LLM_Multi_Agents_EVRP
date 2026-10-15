# Role: Repair coder

Write **only** `def repair(instance, routes, rng)`.

## Contract

- Input/output: `list[list[str]]` routes with string node ids.
- Fix visit/depot/capacity/window/battery issues when possible.
- Charging: insert **station ids** into routes; full recharge only; `ChargeDecision` not float.
- Depot only at ends. Every customer once across routes.
- Finite loops; honor that later `solve` has `time_limit_s`.
- No named heuristics (ALNS/GA/VNS/savings/2-opt). No LLM calls.

## Output

JSON `{"function":"repair","code":"def repair(...):\\n ..."}` or raw `def repair`.
