# Critic Agent — Task

Review the following bounded evaluation evidence.

## Evaluation summary (bounded)
```json
{{evaluation_json}}
```

Answer specifically when possible:
- Why behavior changed on some fixtures but not others.
- Whether generated behavior differs from the handcrafted analogue.
- Whether gains (if any) come from removal logic vs reinsertion.
- For charging/composite: whether actions were rejected, identical, or undone by repair.

Return a CriticReport JSON object. Do not claim objective superiority unless paired deltas clearly support it across seeds.
