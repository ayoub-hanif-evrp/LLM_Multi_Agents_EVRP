from typing import Any

from evrptw_autolab.agents.architect import ArchitectAgent
from evrptw_autolab.agents.base import Agent, extract_json
from evrptw_autolab.agents.charging_engineer import ChargingEngineer
from evrptw_autolab.agents.critic import CriticAgent
from evrptw_autolab.agents.routing_engineer import RoutingEngineer
from evrptw_autolab.agents.schemas import (
    FIXED_ROLES,
    ArchitectPlan,
    CodeFile,
    CodeProposal,
    CriticDecision,
    HandshakeVerdict,
)
from evrptw_autolab.agents.search_engineer import SearchEngineer
from evrptw_autolab.llm.usage import UsageLog

__all__ = [
    "FIXED_ROLES",
    "Agent",
    "ArchitectAgent",
    "ArchitectPlan",
    "ChargingEngineer",
    "CodeFile",
    "CodeProposal",
    "CriticAgent",
    "CriticDecision",
    "HandshakeVerdict",
    "RoutingEngineer",
    "SearchEngineer",
    "build_team",
    "extract_json",
]


def build_team(
    backend: object,
    *,
    model: str,
    temperatures: dict[str, float] | None = None,
    usage_log: UsageLog | None = None,
) -> dict[str, Agent[Any]]:
    """Homogeneous five-agent team: the same model instantiates every role."""
    temps = temperatures or {}
    return {
        "architect": ArchitectAgent(
            backend, model=model, temperature=temps.get("architect", 0.35), usage_log=usage_log
        ),
        "routing": RoutingEngineer(
            backend, model=model, temperature=temps.get("routing", 0.25), usage_log=usage_log
        ),
        "charging": ChargingEngineer(
            backend, model=model, temperature=temps.get("charging", 0.25), usage_log=usage_log
        ),
        "search": SearchEngineer(
            backend, model=model, temperature=temps.get("search", 0.25), usage_log=usage_log
        ),
        "critic": CriticAgent(
            backend, model=model, temperature=temps.get("critic", 0.10), usage_log=usage_log
        ),
    }
