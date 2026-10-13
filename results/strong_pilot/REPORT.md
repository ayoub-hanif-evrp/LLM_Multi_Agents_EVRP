# Strong-model pilot (PILOT_COMMIT=0e4d352 / tip 59cb712)

Selection rule: G4 reach count → 4/4 count → best curriculum_g4_best → G3 reach → lower tokens.
Post-hoc G4 scores are diagnostic only and were not used for selection.

## Winner: qwen3_coder_30b (qwen3-coder:30b)

Best curriculum result: seed 33 at **3/4** G4 (deepest committed gate: multi_customer; G4 stage attempted).

## All rows

| model | seed | deepest | curriculum G4 | posthoc G4 | calls | tokens | hash |
|---|---:|---|---:|---:|---:|---:|---|
| qwen3-coder:30b | 11 | multi_customer | 2 | 2 | 60 | 304439 | a5d2ade9c68ef1e7 |
| qwen3-coder:30b | 22 | charging | 0 | 0 | 52 | 301905 | 267cefecfd479e39 |
| qwen3-coder:30b | 33 | multi_customer | **3** | 3 | 57 | 304662 | 1a4ef51d4d482707 |
| gpt-oss:20b | 11 | multi_customer | 2 | 0 | 34 | 198538 | f3d50f7c7483928a |
| gpt-oss:20b | 22 | routing | 0 | 4* | 12 | 61931 | f0f62ad39e09f446 |
| gpt-oss:20b | 33 | routing | 0 | 0 | 11 | 63181 | 9198a2094c7b8d88 |
| devstral-small-2:24b | 11 | multi_customer | 0 | 0 | 39 | 184585 | 98b3b1b392635a0a |
| devstral-small-2:24b | 22 | routing | 0 | 0 | 50 | 303028 | bb67916964474d1d |
| devstral-small-2:24b | 33 | routing | 0 | 0 | 50 | 300915 | 036cfcd1acfe90d8 |

\* posthoc only — not used for selection. GPT-OSS often failed Architect with empty Ollama content.
