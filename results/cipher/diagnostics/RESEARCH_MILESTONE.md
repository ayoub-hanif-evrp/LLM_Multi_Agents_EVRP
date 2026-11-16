# Research milestone — 2026-11-16

## Repository state

- Active remote branch: **`master` only**
- Deleted identical remote/local branch: `perf/cipher-solver-throughput` (was the same SHA as `master`)
- Archive tags retained: `archive/main-unrelated-history`, `archive/pre-cipher-61cdc20`
- Historical Nov 10 live artifact preserved: `results/cipher/live_signal/ollama_signal.json`

## Engineering verdict

**Go for solver engineering.** Matched before/after vs `e6d94cf` shows median speedups of about 1.5×–5.9× on the six development instances with full feasibility. Warm-worker cold/warm/recovery equivalence holds on the tested Schneider/Hiermann cases. Profiler ranking and proposal-cache provenance were corrected.

## Live LLM discovery gate (Phase 3)

Artifact: `results/cipher/live_signal/ollama_signal_2026-11-16.json`

| Field | Value |
|-------|-------|
| Model | `qwen2.5-coder:14b` (`qwen25_coder_14b`) |
| Digest | `9ec8897f747e246e970bc5cfdda85d22f1123dc2e3d34978a010a75968716849` |
| Calls / tokens | 2 calls; 523 prompt + 348 completion |
| Cache hits | 0 |
| Critic revision scope | applicability_rule_only (scoring expression not revised) |
| Gate | **`behaviorally_inert`** |
| Diagnosis | applicability score non-positive → classical fallback; no changed decision |
| Paired family solves | skipped (gate failed before pairing) |

The model proposed a syntactically admitted operator with `applicability_rule = route_utilization - 0.9`, which abstained on the four-node development repair. No counterexamples were mined; the critic did not run. This failure is recorded once — the prompt was not re-rolled for a lucky success.

## Research go / no-go

| Requirement | Status |
|-------------|--------|
| Trusted EVRP evaluation | Go |
| Faster classical optimizer (matched evidence) | Go |
| Live LLM produces valid, behavior-changing, improving operator | **No-go** |
| Critic/counterexample ablation value | Not reached |
| Cross-family transfer | Not reached |
| Publication-ready claim | **No** |

**Decision: engineering go / research no-go.** Do not scale to multi-family ablations until a single live operator passes the development gate (changed decision + feasible native-objective improvement) under a matched budget. Reconsider the applicability/scoring search space and prompt contracts before enlarging campaigns.
