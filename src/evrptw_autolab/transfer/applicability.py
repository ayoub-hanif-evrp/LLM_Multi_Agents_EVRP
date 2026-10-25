"""A one-feature rule fit only on development outcomes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from evrptw_autolab.transfer.counterexamples import refuse_non_development


@dataclass(frozen=True)
class ApplicabilityExample:
    features: dict[str, float]
    improved: bool
    partition: str


@dataclass(frozen=True)
class ApplicabilityStump:
    """Apply when one feature is on the indicated side of a threshold."""

    feature: str
    threshold: float
    greater_is_apply: bool
    trained: bool

    def rule(self) -> str:
        if not self.trained:
            return "0"
        if self.greater_is_apply:
            return f"{self.feature} - {self.threshold}"
        return f"{self.threshold} - {self.feature}"

    def predicts_apply(self, features: dict[str, float]) -> bool:
        if not self.trained:
            return False
        value = float(features[self.feature])
        if self.greater_is_apply:
            return value > self.threshold
        return value < self.threshold


def fit_stump(examples: Sequence[ApplicabilityExample]) -> ApplicabilityStump:
    """Pick the development split with the best accuracy. A useless split abstains."""
    if not examples:
        raise ValueError("applicability fitting needs development examples")
    for example in examples:
        refuse_non_development(example.partition)
    names = sorted(examples[0].features)
    majority = sum(1 for example in examples if example.improved) >= (len(examples) / 2)
    best_correct = sum(1 for example in examples if example.improved is majority)
    best: ApplicabilityStump | None = None
    for name in names:
        values = sorted({float(example.features[name]) for example in examples})
        cuts = [(left + right) / 2 for left, right in zip(values, values[1:], strict=False)]
        for cut in cuts:
            for greater in (True, False):
                correct = 0
                for example in examples:
                    value = float(example.features[name])
                    predicted = value > cut if greater else value < cut
                    if predicted is example.improved:
                        correct += 1
                if correct > best_correct:
                    best_correct = correct
                    best = ApplicabilityStump(name, cut, greater, True)
    if best is None:
        return ApplicabilityStump("customer_count", 0.0, True, False)
    return best
