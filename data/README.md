# Data

Primary Schneider instances: `dataset/schneider/raw_instances/` (92 EVRPTW files).

Additional families live under `dataset/` (Montoya, Bezzi, Goeke, Hiermann). Validate parsers with:

```text
uv run voltforge datasets validate
```

Partitions for Schneider: **C1+R1 discovery**, **C2+R2+RC1 confirmation**, **RC2 held out**. See `docs/BENCHMARK_CONTRACT.md` and `docs/v2/VARIANT_CONTRACTS.md`.

Frozen Schneider contract metadata: `data/contracts/schneider_v1.0.json`.
