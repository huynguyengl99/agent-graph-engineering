from pydantic_ai import Agent

from triage.agents.deps import TicketContext
from triage.agents.factory import build_model
from triage.core.config import settings
from triage.outputs.triage import TicketAnswer
from triage.prompts import ANSWER_PROMPT

answer_agent = Agent(
    build_model(settings.answer_model),
    output_type=TicketAnswer,
    deps_type=TicketContext,
    instrument=True,
    instructions=ANSWER_PROMPT,
)
