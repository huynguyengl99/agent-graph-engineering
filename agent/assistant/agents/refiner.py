from assistant.agents.base import BaseAgent
from assistant.agents.config import ModelPurpose
from assistant.outputs.knowledge import RefinedQuery
from assistant.prompts import REFINE_PROMPT


class RefinerAgent(BaseAgent[RefinedQuery]):
    """Rewrites a search that found nothing. A decision, not prose."""

    purpose = ModelPurpose.DECISION
    output_type = RefinedQuery
    instructions = REFINE_PROMPT
