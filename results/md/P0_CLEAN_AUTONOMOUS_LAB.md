# P0 clean autonomous lab

Governing rule: the fixed laboratory may expose failures. It must never convert
a failed candidate into a better EVRPTW candidate by injecting solver code.

## Changes in this release

1. Handcrafted recovery solver moved to `baselines/handcrafted_recovery_baseline.py`
2. Removed from bootstrap / compile / runtime / evidence repair
3. Specialist handoff refreshes `current_files` before every role
4. Failed children stay on disk (immutable candidates; REVERT only moves elite pointer)
5. Architect no longer defaults `target` → SEARCH
6. Coding roles prefer raw Python via `write_python`
7. Elite selection uses a fixed acceptance panel (c101C5, c103C5, r104C5, r105C5)
8. Structured mechanism memory scoring
9. Private perturbed instances execute via JSON materialization in the sandbox
10. Fidelity `passed` means promotion_eligible (full feasible_rate), not merely no-crash
11. Ollama records `prompt_eval_count` / `eval_count` into usage

## What v8 was

`discovery_v8` results are **development diagnostics / recovery-baseline results**,
not evidence that Qwen / DeepSeek / CodeLlama independently synthesized those solvers.
All three elites were byte-identical to the handcrafted recovery entry.

## Next experiment

One clean Qwen2.5-Coder 7B campaign from an empty workspace (`discovery_p0_clean`).
Do not run the three-model comparison until that protocol shows autonomous progress.
