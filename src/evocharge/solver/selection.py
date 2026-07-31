"""Adaptive roulette-wheel operator selection."""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class AdaptiveWeights:
    names: list[str]
    weights: dict[str, float] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    uses: dict[str, int] = field(default_factory=dict)
    reaction: float = 0.2

    def __post_init__(self) -> None:
        for n in self.names:
            self.weights.setdefault(n, 1.0)
            self.scores.setdefault(n, 0.0)
            self.uses.setdefault(n, 0)

    def select(self, rng: random.Random) -> str:
        total = sum(self.weights[n] for n in self.names)
        pick = rng.random() * total
        acc = 0.0
        for n in self.names:
            acc += self.weights[n]
            if pick <= acc:
                return n
        return self.names[-1]

    def reward(self, name: str, amount: float) -> None:
        self.scores[name] += amount
        self.uses[name] += 1

    def adapt(self) -> None:
        for n in self.names:
            if self.uses[n] > 0:
                segment = self.scores[n] / self.uses[n]
                self.weights[n] = (1 - self.reaction) * self.weights[n] + self.reaction * max(
                    segment, 0.05
                )
            self.scores[n] = 0.0
            self.uses[n] = 0
