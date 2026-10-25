# Migration to CIPHER-EVRP

Active branch: `research/cipher-evrp`.

Archival branch: `archive/pre-cipher-61cdc20`.

Archived commit: `61cdc20625061c4a11f31c0f9ddbe6f9bb6d3a78`.

That commit is also on `origin/master`, `origin/recovery/policy-dd5949d`, and `origin/research/completion-d5853ee`. History was not rewritten. The four untracked `results/v2/campaigns/*/partial.json` checkpoints were left in the working tree and were not deleted.

## What the archive contains

The archived tree is the previous VoltForge stack: five-agent route construction, expression-policy pilots, structured synthesis, evolutionary campaigns, and the result files under `results/`.

## Kept in the active branch

| Path | Role |
| --- | --- |
| `dataset/` | Schneider, Montoya, Bezzi, Goeke, and Hiermann instances. Files were not edited. |
| `src/evrptw_autolab/problem/` | Legacy Schneider mathematics required by the v2 adapters, plus `problem/v2/` and `problem/datasets/`. |
| `src/evrptw_autolab/backbone/` | Charging completion, Bezzi recharge packing, energy repair, nonlinear charging, local search, construction, and ALNS. |
| `src/evrptw_autolab/llm/` | Ollama, OpenAI-compatible backends, the model registry, and usage accounting. |
| `src/evrptw_autolab/evaluation/` | Independent Schneider fidelity checks used by retained tests. |
| `src/evrptw_autolab/baselines/classical_pilot.py` | The recorded classical development-panel runner. |
| `results/manifests/` | Dataset split and hash manifest. |
| `docs/BENCHMARK_CONTRACT.md`, `docs/v2/` | Mathematical contracts. |

## Removed from the active branch

| Path | Former role |
| --- | --- |
| `src/evrptw_autolab/agentic_v2/` | Five-agent route construction. |
| `src/evrptw_autolab/agents/` | Architect, critic, and specialist conversation loop. |
| `src/evrptw_autolab/components/` | Expression scoring policies and their evolution loop. |
| `src/evrptw_autolab/evolution/` | Patch-based solver evolution. |
| `src/evrptw_autolab/experiments/` | Matched pilots, recovery v2/v4, and campaign runners. |
| `src/evrptw_autolab/sandbox/` | Static scan and subprocess execution of generated Python. |
| `src/evrptw_autolab/structured/` | Monolithic solver synthesis. |
| `src/evrptw_autolab/synthesis/` | From-scratch solver generation. |
| `results/agentic_v2/`, `results/paper/`, `results/previous_campaign/`, `results/recovery_v1/`, `results/recovery_v2/`, `results/recovery_v4/`, `results/structured/`, `results/v2/`, and the other campaign output directories | Historical run artifacts. The archive commit still holds them. |

## New active modules

| Path | Role |
| --- | --- |
| `src/evrptw_autolab/discovery/schemas.py` | `OperatorSpec`. |
| `src/evrptw_autolab/transfer/hard_compatibility.py` | Capability rejection that a model cannot override. |
| `src/evrptw_autolab/discovery/policy_language.py` | Bounded arithmetic scoring. No imports or host access. |
| `src/evrptw_autolab/transfer/selective_controller.py` | Apply, abstain, or classical fallback. |
| `src/evrptw_autolab/transfer/search_decision.py` | Selective insertion among screened repairs. |
| `src/evrptw_autolab/transfer/counterexamples.py` | Evaluator-backed regression records, replay, and minimization. |

`repair_greedy` uses the controller for a caller-supplied `OperatorSpec`. The default solver does not pass one. The multi-agent discovery loop and the B0–B6 experiment campaign are not implemented on this branch.
