from assistant.agents.base import BaseAgent
from assistant.agents.config import ModelPurpose
from assistant.outputs.triage import TriageDecision
from assistant.prompts import DECISION_PROMPT


class DecisionAgent(BaseAgent[TriageDecision]):
    purpose = ModelPurpose.DECISION
    output_type = TriageDecision
    instructions = DECISION_PROMPT
