from evrptw_autolab.agents.base import Agent
from evrptw_autolab.agents.schemas import CodeProposal


class SearchEngineer(Agent[CodeProposal]):
    role = "search"
    prompt_name = "search.md"
    schema = CodeProposal
