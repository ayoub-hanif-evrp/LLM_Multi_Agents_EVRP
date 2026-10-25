# Draft note

This note records what the current CIPHER-EVRP code does. It is not a claim that the hypothesis is true.

## Question

Can an operator stored with a physical compatibility check and an applicability rule avoid a regression that appears when the same operator is applied unconditionally?

## What was measured

The comparison is one Schneider-style repair on a four-node development case, seed 1, with no model calls. Native objective is vehicles, then distance.

| Arm | Objective | Against the classical repair |
| --- | --- | --- |
| B0 classical | 1 vehicle, distance 24 | baseline |
| B1 best scripted expression | 1 vehicle, distance 24 | tie |
| B2 fitness revision to the safe expression | 1 vehicle, distance 24 | tie |
| B3 always apply the longer-detour score | 1 vehicle, distance 30.4339811320566 | loss |
| B4 replace that score with distance | 1 vehicle, distance 24 | tie |
| B5 selective fallback | 1 vehicle, distance 24 | tie |
| B6 non-model stump on the same features | 1 vehicle, distance 24 | tie |

The sample size is 1. No significance claim is made. The selective arms did not beat the classical repair. They avoided the regression caused by always applying the longer detour.

A separate two-point stump, fit only on development and discovery labels, applies when route utilization is high and abstains when it is low. A confirmation label is refused at fit time. The frozen four-node rule was evaluated once on the confirmation partition and was not refit.

## What was not measured

No live Qwen run was made. Destroy, charging, and fleet operators can change a decision in unit tests; they were not part of the B0–B6 table. The five benchmark families were not compared in one average. Schneider RC2 remains a previously inspected set, and no untouched final test has been declared.
