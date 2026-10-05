from assistant.agents.base import BaseAgent
from assistant.agents.config import ModelPurpose
from assistant.outputs.support import TicketAnswer
from assistant.prompts import TEAM_PROMPT


class TeamAgent(BaseAgent[TicketAnswer]):
    """Answers the support agent."""

    purpose = ModelPurpose.ANSWER
    output_type = TicketAnswer
    instructions = TEAM_PROMPT
