# Experimental protocol

## Partitions

| Partition | Allowed use |
|-----------|-------------|
| `development` / `discovery` | operator proposal, counterexample mining, applicability fitting, classical freeze, live signal |
| `confirmation` | frozen evaluation only; mining refused |
| `heldout` | untouched until a predeclared protocol; mining refused |

Schneider RC2 remains previously inspected and is never labeled blind.

## Classical freeze

`uv run voltforge research freeze-classical` writes `results/cipher/classical/development_panel.json` for a small Schneider+Hiermann development panel with zero LLM calls.

## Live signal gate

`uv run voltforge research live-signal [--backend fake|ollama] [--live]` discovers one capped operator and, when the discovery decision changes behavior, compares classical vs policy on Schneider `c101C5` and Hiermann `c101_21`.

Stop rules: schema/capability failure, no behavior change, or feasibility regression. Do not raise call caps to force a positive result. The recorded Ollama artifact may be an honest `behaviorally_inert` or `discovery_failed` gate.

## Scripted B0–B6

`uv run voltforge research report` writes the scripted four-node comparison. It uses no live model and is not a significant multi-instance result.

## Reporting rules

- Report discovery cost and deployment cost separately.
- Do not average native objectives across families.
- Classical runs must show `policy_executed=false` and `llm_calls=0`.
- Selective runs must report `changed_decisions` when the operator diverges.
