# VoltForge discovery package

**Date:** 2026-09-05
**Protocol:** five agents, homogeneous model, discovery families C1+R1 only.
**Not opened:** confirmation (C2, R2, RC1) for evolution; RC2 held-out.

## Environment

- Python: `3.14.4 (tags/v3.14.4:23116f9, Apr  7 2026, 14:10:54) [MSC v.1944 64 bit (AMD64)]`
- Platform: `Windows-11-10.0.26200-SP0`
- Ollama: `ollama version is 0.32.3`
- Cycles: 8
- Solver wall-clock: 30.0 s

## Model comparison

| Model | Status | Compile-valid | F1 feasible | c101C5 vehicles | c101C5 distance | Small feasible / 36 | Exact fleet | LLM calls | Wall s |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| qwen2.5-coder:7b | ran | False | 0.0 | 0 | 0.0 | 0 | 0 | 102 | 1243.5 |

Spark-era F1=1.0 results are **not** in this table. Those used a hidden stitch.

Raw JSON: `tables/raw_autolab/discovery_p0_clean_*.json`. Elite solvers: `solvers/discovery_p0_clean/<model_id>/`.

