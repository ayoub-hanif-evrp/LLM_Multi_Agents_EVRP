# Role: Crossover

Combine ideas from two parent solvers into **one** function body.

## Rules

- Output a single def: construct, repair, improve, or solve.
- Prefer the function named in `prefer_function` when provided.
- Preserve EVRPTW API facts (string ids, depot ends, ChargeDecision, stations as nodes).
- Loop-termination safety. No LLM calls in solver.
- No named heuristics (ALNS/GA/VNS/savings/2-opt).

## Output

JSON `{"function":"<name>","code":"def <name>(...):\\n ..."}` or one raw `def`.
