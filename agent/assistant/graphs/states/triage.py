from typing import Annotated

from pydantic import BaseModel

from assistant.agents import TicketContext
from assistant.graphs.states.reducers import last_wins
from assistant.outputs.triage import Classification, TicketAnswer, TriageDecision


class TriageState(BaseModel):
    """State threaded through the triage graph.

    A model, not a TypedDict: LangGraph validates on the way in, so a node is
    handed its own types. Everything but the ticket defaults.
    """

    context: TicketContext
    classification: Classification | None = None
    decision: TriageDecision | None = None
    # Seeded here and read by the knowledge subgraph. Its own bookkeeping
    # (attempts, exhaustion) stays inside it.
    kb_query: str = ""
    kb_snippets: Annotated[list[str], last_wins] = []
    answer: TicketAnswer | None = None
    escalation_reason: str = ""
    tool_error: str = ""
    approval_granted: bool = False
    delivery_receipt: str = ""
    guardrail_findings: Annotated[list[str], last_wins] = []
    reply_blocked: bool = False
