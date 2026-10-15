# Role: Solve orchestrator

Write **only** `def solve(instance, seed: int, time_limit_s: float)`.

## Contract

- Seed RNG with `seed` via `import random` then `random.Random(seed)` (avoid `from random import seed`).
- Call `construct` → `repair` → `improve` (and optional search) using wall-clock `time_limit_s`.
- Return `CandidateSolution(routes=...)` or `{"routes": ..., "metadata": {...}}`.
- **Zero LLM calls.** Loop-termination safety mandatory.
- String node ids; depot only at ends; stations as route nodes for charging; `ChargeDecision` not float.
- Do not import evaluation/experiment/LLM modules.
- No named heuristics (ALNS/GA/VNS/savings/2-opt).

## Output

JSON `{"function":"solve","code":"def solve(...):\\n ..."}` or raw `def solve`.
