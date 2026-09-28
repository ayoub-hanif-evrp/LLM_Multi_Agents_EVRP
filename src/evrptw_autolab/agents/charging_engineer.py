from evrptw_autolab.agents.base import Agent
from evrptw_autolab.agents.schemas import CodeProposal


class ChargingEngineer(Agent[CodeProposal]):
    role = "charging"
    prompt_name = "charging_engineer.md"
    schema = CodeProposal
