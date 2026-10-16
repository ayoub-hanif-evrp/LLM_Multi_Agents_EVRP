# Matched Qwen3-Coder campaign (development panel, 5 families)

**Commit at launch:** `6f2e3aa` / prior tooling `200bb9f`  
**Model:** `qwen3-coder:30b` (local Ollama)  
**Seed:** 7  
**Panel (one per family):** `c101C5`, `tc0c10s2cf1`, `C101-5`, `c101C6`, `c101_21`  
**Budgets:** solver `time_limit_s=5`, evolution `generations=1`, `max_llm_calls=30`, wall ≈434s

## Aggregate

| Arm | Feasible | Mean wall (s) | LLM tokens | Notes |
|---|---|---|---|---|
| classical | 5/5 | 8.8 | 0 | Human backbone |
| single_agent | 5/5 | 18.2 | 1 030 | **0 genuine LLM components** (syntax fallbacks) |
| five_agent | 5/5 | 22.9 | 9 980 | 1 genuine LLM component / instance; objectives unchanged |
| five_agent_evolution | 5/5 panel-feasible | 36.9 | 13 105 | Attribution `pure_classical` |

## Per-instance objectives (classical = agent arms)

| Instance | Classical / agents objective |
|---|---|
| Schneider `c101C5` | 2.0 vehicles |
| Montoya `tc0c10s2cf1` | 32.115 duration |
| Bezzi `C101-5` | 227 recharge cost |
| Goeke `c101C6` | 2.0 vehicles |
| Hiermann `c101_21` | 4220.9 cost |

## Causal conclusion (this run)

**No multi-agent improvement over classical was demonstrated.**  
Feasibility matches the backbone. Generated component code frequently failed syntax validation and was replaced by `DEFAULT_SOURCES` (correctly not counted as LLM discoveries). Where one component validated, objectives did not improve vs classical under matched solver budgets.

This is a negative/null result for the LLM contribution claim on this small panel and budget — not a paper win.

## Files

- `campaign.json` — full config + rows  
- `rows.jsonl` — one record per arm×instance  
- `qwen_campaign_console.log` — console (validation warnings)
