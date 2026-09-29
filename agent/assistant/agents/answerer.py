from pydantic_ai import Agent

from assistant.agents.deps import TicketContext
from assistant.agents.factory import build_model
from assistant.core.config import settings
from assistant.outputs.triage import TicketAnswer
from assistant.prompts import ANSWER_PROMPT

answer_agent = Agent(
    build_model(settings.answer_model),
    output_type=TicketAnswer,
    deps_type=TicketContext,
    instrument=True,
    instructions=ANSWER_PROMPT,
)
