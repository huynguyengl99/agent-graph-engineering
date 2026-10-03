from assistant.agents.base import BaseAgent
from assistant.agents.config import ModelPurpose
from assistant.outputs.support import Decision
from assistant.prompts import DECISION_PROMPT


class DecisionAgent(BaseAgent[Decision]):
    """What the message needs before it can be answered."""

    purpose = ModelPurpose.DECISION
    output_type = Decision
    instructions = DECISION_PROMPT
