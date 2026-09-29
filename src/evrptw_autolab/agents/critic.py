from evrptw_autolab.agents.base import Agent
from evrptw_autolab.agents.schemas import CriticDecision, HandshakeVerdict


class CriticAgent(Agent[CriticDecision]):
    role = "critic"
    prompt_name = "test_evolution_critic.md"
    schema = CriticDecision

    def handshake(self, payload: dict) -> HandshakeVerdict:
        previous = self.schema
        self.schema = HandshakeVerdict  # type: ignore[assignment]
        try:
            result = self.run({**payload, "task": "HANDSHAKE"})
        finally:
            self.schema = previous
        if isinstance(result, HandshakeVerdict):
            return result
        return HandshakeVerdict.model_validate(result)
