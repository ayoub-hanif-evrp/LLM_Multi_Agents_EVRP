# Experiment A repair audit — DeepSeek 4/4 → 12/12 C5

**Artifact:** `results/md/artifacts/p1_3/P1_3_FIRST_4OF4_SOLVER/`
**Diff:** `SEED_TO_REPAIR.diff`

## Instance-specific constants

**NONE**

- No hardcoded customer/station string literals (`C78`, `S1`, …)
- No instance names (`r105C5`, …)
- No hardcoded coordinates

## What the patch changed (generic)

Starting from the Qwen 3/4 dedicated-route seed, DeepSeek:

1. Kept one `depot → customer → depot` route per customer.
2. Still uses `propagate_route` and inserts a station when battery goes negative.
3. Changed the insertion-index scan to also require the next stop’s `service_start` to respect the current node’s `due_time` before advancing `k`.

That is a generic feasibility tweak, not an `r105`-specific hardcode — consistent with 12/12 C5 generalization.
