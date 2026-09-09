# FINAL repair vs synthesis

Observed capability differences (n=5/model; not claimed as statistical significance).

| Model | Empty-workspace synthesis | Repair existing solver |
| --- | --- | --- |
| Qwen 7B | G2=3/5, G3=3/5, reached G4=3/5, G4 4/4=0/5 | 0/5 4/4 |
| DeepSeek 6.7B | G1=1/5, G2=0/5, G3=0/5 | 0/5 4/4 |
| CodeLlama 7B | G1=4/5, G2=1/5, G3=1/5, reached G4=1/5 | 0/5 4/4 |

## Interpretation

If DeepSeek repair success ≫ synthesis success while Qwen synthesis ≫ DeepSeek synthesis,
model ranking reverses by task: repair vs from-scratch synthesis are distinct capabilities.
