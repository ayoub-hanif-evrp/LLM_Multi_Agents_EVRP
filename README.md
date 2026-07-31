# EvoCharge — lean Schneider EVRPTW optimization

Verifier-grounded multi-agent discovery of EVRPTW search operators on the
**Schneider Solomon E-VRPTW** dataset.

## Architecture

```
dataset/schneider  →  parse  →  construct / ALNS
                                 ↑
agents + prompts → candidates → operators (handcrafted + generated)
```

| Layer | Role |
|-------|------|
| `dataset/schneider/` | Instances (depot, customers, stations, EV params Q/C/r/g/v) |
| `domain/` | Instance, Vehicle, Solution, objective, charging model |
| `solver/` | Construction, feasibility, charging repair, ALNS |
| `operators/` | Handcrafted destroy/repair + generated-operator API |
| `agents/` + `prompts/` | Analyst / Scientist / Coder via local Ollama |
| `candidates/` + `verification/` | Bounded codegen + sandbox gates |
| `evolution/` | Optional population loop over verified operators |

## Setup

```bash
uv sync
uv run evocharge build-contract
uv run evocharge baseline construct --instance dataset/schneider/raw_instances/c101C5.txt
uv run evocharge baseline run --config configs/schneider_main.yaml --instance dataset/schneider/raw_instances/c101C5.txt
uv run evocharge full-stack-run --candidate m9b_main_20260728_seed_h1
```

Configs (only three): `configs/base.yaml`, `configs/schneider_main.yaml`, `configs/agents.yaml`.

## EV model (per instance)

Homogeneous fleet with battery `Q`, load `C`, consumption `r`, velocity `v`,
linear full recharge via inverse rate `g`.

## License

MIT — see [LICENSE](LICENSE).
