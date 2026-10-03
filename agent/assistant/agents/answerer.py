from assistant.agents.base import BaseAgent
from assistant.agents.config import ModelPurpose
from assistant.outputs.support import TicketAnswer
from assistant.prompts import ANSWER_PROMPT


class AnswerAgent(BaseAgent[TicketAnswer]):
    purpose = ModelPurpose.ANSWER
    output_type = TicketAnswer
    instructions = ANSWER_PROMPT
