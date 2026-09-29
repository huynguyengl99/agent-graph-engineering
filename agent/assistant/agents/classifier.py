from pydantic_ai import Agent

from assistant.agents.deps import TicketContext
from assistant.agents.factory import build_model
from assistant.core.config import settings
from assistant.outputs.triage import Classification
from assistant.prompts import CLASSIFIER_PROMPT

classifier_agent = Agent(
    build_model(settings.decision_model),
    output_type=Classification,
    deps_type=TicketContext,
    instrument=True,
    instructions=CLASSIFIER_PROMPT,
)
