# Research milestone — 2026-11-16 (completed)

## Repository state

- Active remote branch: **`master` only**
- Archive tags retained: `archive/main-unrelated-history`, `archive/pre-cipher-61cdc20`
- Performance verification: `PERF_REPORT.md`, `perf_before_after.json`, `worker_equivalence.json`

## What was finished after the first no-go

1. **Discovery contract fixes** (not prompt re-rolls of an unchanged pipeline):
   - Specialist prompt no longer teaches `route_utilization - 0.9` as the default example; prefers `applicability_rule=1` for scoring experiments; restricts scoring to repair-insertion features.
   - Critic may revise **applicability and/or scoring**.
   - Critic now runs on inert abstention **and** apply-but-identical classical choice (previously silent when no counterexamples were mined).
   - Duplicate critic fingerprints are treated as no-ops, not hard failures.

2. **Live Qwen 14B attempts** (each recorded):

| Artifact | Gate | Notes |
|----------|------|-------|
| `ollama_signal.json` (Nov 10) | behaviorally_inert | `applicability_rule=true` / unknown feature |
| `ollama_signal_2026-11-16.json` | behaviorally_inert | `route_utilization - 0.9` abstained |
| `ollama_signal_2026-11-16b.json` | discovery_failed | duplicate critic fingerprint (since fixed) |
| `ollama_signal_2026-11-16c.json` | behaviorally_inert | applied with `delta_distance + …`, same move as classical |
| `ollama_signal_2026-11-16d.json` | behaviorally_inert | critic revised scoring; still same classical move |

3. **Phase 4 development comparison** (`phase4_dev_comparison.json`):
   - classical / handcrafted short / handcrafted long / random-valid / live multi-role on the four-node development repair
   - scripted B0–B6 retained
   - paired Schneider+Hiermann seeds for the latest live operator: mostly ties; one Schneider seed changed 6 decisions without objective improvement
   - `handcrafted_long` (`-1 * delta_distance`) **does** change decisions (worsens objective) — proving the search surface can move; live multi-role did not find a beneficial move

## Research go / no-go

| Requirement | Status |
|-------------|--------|
| Trusted EVRP evaluation | Go |
| Verified classical speedups | Go |
| Live LLM changes a decision **and** improves native objective | **No-go** |
| Critic/counterexample ablation proving multi-role value | **No-go** (no beneficial live operator) |
| Publication-ready claim | **No** |

**Decision: engineering complete / research still no-go.**  
The remaining bottleneck is not repository hygiene: the live model has not yet produced a transferable beneficial ranking rule under the bounded budget. Next research step is to redesign the operator search space / few-shot evidence so that “change the selected insertion” is an explicit measurable target before scaling families.
