from pydantic_ai import Agent

from triage.agents.deps import TicketContext
from triage.agents.factory import build_model
from triage.core.config import settings
from triage.outputs.triage import Classification
from triage.prompts import CLASSIFIER_PROMPT

classifier_agent = Agent(
    build_model(settings.decision_model),
    output_type=Classification,
    deps_type=TicketContext,
    instrument=True,
    instructions=CLASSIFIER_PROMPT,
)
