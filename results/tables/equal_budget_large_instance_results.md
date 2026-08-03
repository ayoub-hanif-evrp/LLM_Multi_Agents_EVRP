_Win/tie/loss against RANDOM_RANKING on the (vehicles, distance) lexicographic score, large (56-instance) subset only. Distance deltas are computed only over instance pairs where the paired median vehicle counts are equal._

| method | n_instances | win_vs_random | tie_vs_random | loss_vs_random | median_vehicles | median_distance | distance_comparable_pairs | mean_distance_delta_vs_random_when_fleet_equal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HANDCRAFTED_CHARGING_RANKING | 56 | 16 | 25 | 15 | 24 | 2687 | 56 | -1.541 |
| HANDCRAFTED_COMBINED_RANKING | 56 | 43 | 7 | 6 | 24 | 2656 | 52 | -28.45 |
| HANDCRAFTED_TIME_RANKING | 56 | 19 | 24 | 13 | 24 | 2656 | 56 | -10.29 |
| RANDOM_RANKING | 56 | 0 | 0 | 0 | 24 | 2692 | 0 | nan |
| REFERENCE_DSL_RANKING | 56 | 43 | 8 | 5 | 24 | 2656 | 52 | -28.08 |
