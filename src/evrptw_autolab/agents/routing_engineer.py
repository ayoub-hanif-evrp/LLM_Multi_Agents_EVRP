from evrptw_autolab.agents.base import Agent
from evrptw_autolab.agents.schemas import CodeProposal


class RoutingEngineer(Agent[CodeProposal]):
    role = "routing"
    prompt_name = "routing_engineer.md"
    schema = CodeProposal
