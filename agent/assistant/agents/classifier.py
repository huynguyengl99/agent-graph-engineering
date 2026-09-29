from assistant.agents.base import BaseAgent
from assistant.agents.config import ModelPurpose
from assistant.outputs.triage import Classification
from assistant.prompts import CLASSIFIER_PROMPT


class ClassifierAgent(BaseAgent[Classification]):
    purpose = ModelPurpose.DECISION
    output_type = Classification
    instructions = CLASSIFIER_PROMPT
