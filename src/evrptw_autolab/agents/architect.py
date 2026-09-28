from evrptw_autolab.agents.base import Agent
from evrptw_autolab.agents.schemas import ArchitectPlan


class ArchitectAgent(Agent[ArchitectPlan]):
    role = "architect"
    prompt_name = "solver_architect.md"
    schema = ArchitectPlan
