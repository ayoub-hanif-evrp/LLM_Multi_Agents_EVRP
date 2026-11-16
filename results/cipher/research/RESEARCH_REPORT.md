# CIPHER-EVRP research-results sprint

Base: `master` @ `0344694` (plus this experimental commit)  
Priority: measured scientific signal, not infrastructure.

## Executive conclusion

**Search-space go / LLM discovery no-go (under this budget).**

1. Real development trajectories contain measured improvement opportunities (35.9% of audited checkpoints).
2. Simple non-LLM policies already exploit part of that headroom on Schneider development seeds.
3. Evidence-guided Qwen2.5-Coder 14B proposals (single-LLM and multi-role) were valid and behavior-changing, but **regressed** native objectives.
4. Multi-role did not beat an equally budgeted single-LLM baseline (both converged to the same harmful `battery_margin` rule).
5. No LLM-discovered policy is frozen for confirmation transfer. The handcrafted `delta_distance` oracle reproduces Schneider `c101_21` development wins under always-on use, but selective gating and cross-family transfer remain ties.

---

## Experiment 1 — Improvement headroom

Artifact: `headroom_audit.json`

| Metric | Value |
|--------|------:|
| Runs (family×seed) | 12 |
| Checkpoints with ≥2 feasible insertions | 39 |
| Checkpoints with better downstream alternative | 14 |
| Opportunity fraction | **35.9%** |
| Decision | `continue_to_live_discovery` |

Selection procedure was predeclared: classical = minimum immediate acceptance; alternatives = farthest / median / best `battery_margin` / random; equal continuation seed and budget.

Example (Schneider `c101C5`, seed 7): classical immediate acceptance 113.7 → final (3 vehicles, 292.1); an alternative acceptance 159.3 → final (2 vehicles, 260.9). Immediate greed is not identical to downstream quality.

---

## Experiment 2–3 — Live discovery + matched controls

Artifact: `evidence_discovery.json`  
Model: `qwen2.5-coder:14b`  
LLM budget used: 10 calls / 34934 prompt + 1152 completion tokens (after compact-prompt repair)

### Table A — Solution quality / feasibility (development panel)

Paired seeds `{7,11,22}` on Schneider `c101C5`, Schneider `c101_21`, Hiermann `c101_21`.  
Wins/ties/losses are vs classical `policy=None` on the **same** current backbone.

| Method | Gate | Wins | Ties | Losses | Changed decisions |
|--------|------|-----:|-----:|-------:|------------------:|
| Classical | baseline | 0 | 9 | 0 | 0 |
| Handcrafted `delta_distance` | **beneficial** | 3 | 6 | 0 | 150 |
| Handcrafted `-1 * delta_distance` | objective_regression | 0 | 1 | 8 | 315 |
| Handcrafted `delta_distance - 0.01 * battery_margin` | **beneficial** | 3 | 6 | 0 | 156 |
| Random-valid `delta_distance + incremental_energy_cost` | **beneficial** | 3 | 6 | 0 | 150 |
| Single-LLM `battery_margin` | objective_regression | 0 | 1 | 8 | 234 |
| Multi-role_0 `battery_margin` | objective_regression | 0 | 1 | 8 | 234 |
| Multi-role_1 `battery_margin` | objective_regression | 0 | 1 | 8 | 234 |
| Multi-role_2 `battery_margin` | objective_regression | 0 | 1 | 8 | 234 |

Schneider `c101_21` drove the handcrafted/random wins (including vehicle-count improvements on seeds 11 and 22). Families are not averaged.

### Table B — Ablations / inference budgets

| Arm | LLM calls (generation) | Notes |
|-----|------------------------:|-------|
| Multi-role ×3 proposals | 9 | architect+specialist+critic each |
| Single-LLM | 1 | matched as one generation call, not three roles |
| Classical / handcrafted / random | 0 | no LLM |

Result: multi-role = single-LLM in policy and outcome (`battery_margin`); **no agent-collaboration advantage** under this matched setup.

Synthetic four-node unchanged decisions no longer block paired real-instance evaluation (`live_signal.py` minimal fix).

---

## Experiment 4 — Transfer (oracle diagnostic only)

Artifact: `transfer_oracle.json`  
Frozen operator: handcrafted `delta_distance` (not LLM).  
Panel: Schneider `c101C5`, Schneider `c101_21`, Hiermann `c101_21`, Montoya `tc0c10s2cf1`, Goeke `c101C6` × seeds `{7,11,22}`.  
Modes: always-on (`applicability=1`), selective (`route_utilization - 0.5`), classical_fallback (null policy reference).

### Table C — Oracle transfer by instance (wins / ties / losses vs classical)

| Mode | Family / instance | Wins | Ties | Losses |
|------|-------------------|-----:|-----:|-------:|
| always_on | Schneider `c101C5` | 0 | 3 | 0 |
| always_on | Schneider `c101_21` | **3** | 0 | 0 |
| always_on | Hiermann `c101_21` | 0 | 3 | 0 |
| always_on | Montoya `tc0c10s2cf1` | 0 | 3 | 0 |
| always_on | Goeke `c101C6` | 0 | 3 | 0 |
| selective_high_util | Schneider `c101C5` | 0 | 3 | 0 |
| selective_high_util | Schneider `c101_21` | 0 | 3 | 0 |
| selective_high_util | Hiermann `c101_21` | 0 | 3 | 0 |
| selective_high_util | Montoya `tc0c10s2cf1` | 0 | 3 | 0 |
| selective_high_util | Goeke `c101C6` | 0 | 3 | 0 |
| classical_fallback | all five instances | 0 | 15 | 0 |

Interpretation: always-on reproduces the Schneider `c101_21` development signal (3/3 improved). Selective applicability nullifies that gain (ties). Cross-family rows stay ties. Classical fallback is identically tied by construction. **No beneficial LLM policy exists to freeze**; cross-family transfer remains unproven even for the oracle.

---

## Paper-ready takeaways (honest)

**What we can claim**
- The CIPHER evaluation/search stack exposes nontrivial repair-decision headroom on real EVRP development instances.
- The restricted `OperatorSpec` scoring language can encode policies that beat classical trajectories on Schneider development seeds.
- Immediate insertion cost and downstream native objective can disagree.

**What we cannot claim**
- That the current multi-agent LLM workflow discovers beneficial EVRP policies.
- That multi-agent collaboration beats a budget-matched single LLM.
- That selective transfer of an LLM policy helps across families.
- That the handcrafted oracle transfers outside Schneider `c101_21` (always-on wins stay instance-local; selective mode ties).

**Decision rules fired**
- Headroom found → continued to live discovery.
- Useful alternatives exist but LLM failed to discover them → report representation/feedback gap (`battery_margin` overfit), not repository failure.
- Multi-role ≤ single-LLM → no collaboration claim.

## Research go / no-go

| Gate | Status |
|------|--------|
| Foundation (evaluator, classical, five families, agents) | **Go** |
| Scientific signal (LLM improves feasible trajectories) | **No-go** |
| Scientific validation (reproducible multi-agent + transfer) | **No-go** |

Next research step (not done here): change the feedback representation so models are scored on **continuation outcomes / vehicle-first objectives**, not feature heuristics that ignore fleet count—before more prompt volume.
