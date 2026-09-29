from pydantic_ai import Agent

from assistant.agents.deps import TicketContext
from assistant.agents.factory import build_model
from assistant.core.config import settings
from assistant.outputs.triage import TriageDecision
from assistant.prompts import DECISION_PROMPT

# A union output_type is the documented way to give the model a choice, but the
# Agent overloads are typed for `type[T] | Sequence[Any]` and reject `X | Y`.
decision_agent: Agent[TicketContext, TriageDecision] = Agent(  # type: ignore[call-overload]
    build_model(settings.decision_model),
    output_type=TriageDecision,
    deps_type=TicketContext,
    instrument=True,
    instructions=DECISION_PROMPT,
)
