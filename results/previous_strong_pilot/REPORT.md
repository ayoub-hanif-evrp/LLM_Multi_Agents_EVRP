# Strong-model selection pilot

Protocol: five-agent patch synthesis · development instances only · max 120 calls **or** 300k tokens · seeds 11/22/33 · `num_ctx=8192`.

Both models installed and smoke-tested on a short Python coding prompt (Ollama 0.33.3).

Label in paper: **stronger local coding-model anchors** (not SLMs).

## Results

| model | seed | deepest stage | best G4 | confirmation | calls | tokens | solver hash | note |
|---|---:|---|---:|---|---:|---:|---|---|
| devstral-small-2:24b | 11 | multi_customer | 0/4 | — | 55 | 305537 | `def00b300320f873` | G0–G3 clear; G4 timeout then NameError |
| devstral-small-2:24b | 22 | multi_customer | 0/4 | — | 33 | 162207 | `16ea7a6c93a93f99` | G0–G3 clear; framework TypeError mid-G4 (fixed after) |
| devstral-small-2:24b | 33 | executable | 0/4 | — | 48 | 305389 | `20d1775ce7bb4a8d` | syntax stall |
| qwen3-coder:30b | 11 | routing | 0/4 | — | 48 | 307421 | `7bf94ff4e8550c20` | stuck on charging (depot/API errors) |
| qwen3-coder:30b | 22 | routing | **2/4** | — | 48 | 307936 | `688dd667a98475bd` | charging timeout; post-hoc panel 2/4 |
| qwen3-coder:30b | 33 | routing | **2/4** | — | 58 | 304349 | `589efad7bc413826` | charging timeout; post-hoc panel 2/4 |

No run reached 3/4 or 4/4 → no confirmation repair, no evolution, no held-out.

## Selection

- **Winner (G4 progression):** `qwen3-coder:30b` — two seeds at **2/4** G4.
- **Loser (reported):** `devstral-small-2:24b` — stronger on early gates (2/3 seeds to G3) but **0/4** G4.

Recommended strong local anchor for the frozen final campaign: **qwen3-coder:30b**. Keep Devstral pilot rows as the model-selection contrast.
