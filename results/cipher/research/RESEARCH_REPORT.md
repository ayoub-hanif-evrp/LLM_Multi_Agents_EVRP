# CIPHER-EVRP research-results sprint

Base: `master` @ `0344694` (plus this experimental commit)  
Priority: measured scientific signal, not infrastructure.

## Executive conclusion

**Search-space go / LLM discovery no-go (under this budget).**  
**New (B0–B4): the prior handcrafted “win” is largely a classical scoring fix.**

1. Real development trajectories contain measured improvement opportunities (35.9% of audited checkpoints) — but classical “acceptance” was **post-insertion total route distance**, not marginal `delta_distance`.
2. B0–B4 ablation shows **B1 (marginal classical) matches B3 (handcrafted `delta_distance`)** on Schneider `c101_21` (3/3 improved vs B0). The OperatorSpec gain is not a sophisticated new strategy.
3. Evidence-guided Qwen2.5-Coder 14B proposals (single-LLM and multi-role) were valid and behavior-changing, but **regressed** native objectives (B4 confirms).
4. Multi-role did not beat an equally budgeted single-LLM baseline (both converged to the same harmful `battery_margin` rule).
5. No LLM-discovered policy is frozen for confirmation transfer. Adopt **B1 as the corrected classical baseline** before further discovery spend.

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

Selection procedure was predeclared: classical = minimum immediate acceptance (**total route distance after insertion**, same as B0); alternatives = farthest / median / best `battery_margin` / random; equal continuation seed and budget.  
**Reinterpretation (after B0–B4):** part of the 14/39 “improvable” checkpoints may be opportunities created by that total-route vs marginal criterion mismatch.

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

## Baseline ablation B0–B4 (classical scoring confound)

Artifact: `baseline_ablation_b0b4.json`  
Panel: Schneider `c101C5`, `c101_21`, `c103C5`, `r104C5`, `rc105C5` × seeds `{7,11,22}`.  
Paired vs B0 (legacy total-route classical). Gates require **no regressions** to call beneficial.

| Arm | Meaning | Wins | Ties | Losses | Gate vs B0 |
|-----|---------|-----:|-----:|-------:|------------|
| B0 | Classical: min post-insertion **total** route distance | 0 | 15 | 0 | baseline |
| B1 | Classical: min **marginal** `delta_distance` | 3 | 11 | 1 | mixed |
| B2 | B1 + light fleet/consolidation bias | 3 | 11 | 1 | mixed |
| B3 | Handcrafted `delta_distance` OperatorSpec on B0 backbone | 3 | 11 | 1 | mixed |
| B4 | LLM `battery_margin` negative control on B0 | 0 | 9 | 6 | objective_regression |

### Table D — by instance (wins / ties / losses vs B0)

| Arm | `c101C5` | `c101_21` | `c103C5` | `r104C5` | `rc105C5` |
|-----|----------|-----------|----------|----------|-----------|
| B1 | 0/3/0 | **3/0/0** | 0/3/0 | 0/2/1 | 0/3/0 |
| B2 | 0/3/0 | **3/0/0** | 0/3/0 | 0/2/1 | 0/3/0 |
| B3 | 0/3/0 | **3/0/0** | 0/3/0 | 0/2/1 | 0/3/0 |
| B4 | 0/0/3 | 0/0/3 | 0/3/0 | 0/3/0 | 0/3/0 |

**Decision (predeclared):** B1 matches B3 on `c101_21` → handcrafted gain is largely explained by correcting the classical insertion criterion. B2 does not beat B1 on this panel. **Adopt B1 as the research classical baseline.** Do not spend the next budget on larger LLMs or more agent roles until residual headroom is re-measured against B1.

Local screening still allows temporary battery debt; all paired outcomes above use the trusted native evaluator only.

---

## Paper-ready takeaways (honest)

**What we can claim**
- The CIPHER evaluation/search stack exposes nontrivial repair-decision headroom on real EVRP development instances — partly attributable to a total-route vs marginal scoring inconsistency in classical repair.
- Correcting classical repair to marginal `delta_distance` (B1) reproduces the prior handcrafted OperatorSpec wins on Schneider `c101_21`.
- Immediate insertion cost and downstream native objective can disagree.

**What we cannot claim**
- That the handcrafted `delta_distance` operator discovered a sophisticated new optimization strategy beyond fixing B0.
- That the current multi-agent LLM workflow discovers beneficial EVRP policies.
- That multi-agent collaboration beats a budget-matched single LLM.
- That selective transfer of an LLM policy helps across families.

**Decision rules fired**
- Headroom found → continued to live discovery (under B0 classical).
- B1 ≈ B3 on `c101_21` → adopt B1 baseline; reinterpret prior E3/E4 oracle wins.
- Useful alternatives exist but LLM failed → representation/feedback gap (`battery_margin` overfit).
- Multi-role ≤ single-LLM → no collaboration claim.

## Research go / no-go

| Gate | Status |
|------|--------|
| Foundation (evaluator, classical, five families, agents) | **Go** |
| Classical scoring correctness (B0→B1) | **Fix adopted as next baseline** |
| Scientific signal (LLM improves feasible trajectories) | **No-go** |
| Scientific validation (reproducible multi-agent + transfer) | **No-go** |

Next research step: re-audit residual headroom **against B1**, then either (a) build a counterfactual rollout dataset + non-LLM ranker if headroom remains, or (b) retarget discovery to route elimination / destroy selection / charging if insertion headroom collapses.
