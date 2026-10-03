from assistant.agents.base import BaseAgent
from assistant.agents.config import ModelPurpose
from assistant.outputs.support import CustomerDecision, Decision, TeamDecision
from assistant.prompts import DECISION_PROMPT


class CustomerDecisionAgent(BaseAgent[Decision]):
    """What a customer's message needs. No tools: it has none to reach for."""

    purpose = ModelPurpose.DECISION
    output_type = CustomerDecision
    instructions = DECISION_PROMPT


class TeamDecisionAgent(BaseAgent[Decision]):
    """What the team's question needs. No escalation: they are who it would
    escalate to."""

    purpose = ModelPurpose.DECISION
    output_type = TeamDecision
    instructions = DECISION_PROMPT
