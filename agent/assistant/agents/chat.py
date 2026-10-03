from assistant.agents.base import BaseAgent
from assistant.agents.config import ModelPurpose
from assistant.prompts import TEAM_PROMPT


class TeamAgent(BaseAgent[str]):
    """Answers the support agent. Plain text, so it streams."""

    purpose = ModelPurpose.ANSWER
    output_type = str
    instructions = TEAM_PROMPT
