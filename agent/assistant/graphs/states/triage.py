from typing import Annotated, TypedDict

from assistant.agents import TicketContext
from assistant.outputs.triage import Classification, TicketAnswer, TriageDecision


def last_wins(_current: object, incoming: object) -> object:
    return incoming


class TriageState(TypedDict, total=False):
    """State threaded through the triage graph.

    Nodes read what they need and write only their own keys. Part 4 revisits
    this once reducers and subgraph isolation matter.
    """

    context: TicketContext
    classification: Classification
    decision: TriageDecision
    # Seeded here and read by the knowledge subgraph. Its own bookkeeping
    # (attempts, exhaustion) stays inside it.
    kb_query: str
    kb_snippets: Annotated[list[str], last_wins]
    answer: TicketAnswer
    escalation_reason: str
    tool_error: str
    approval_granted: bool
    delivery_receipt: str
    guardrail_findings: Annotated[list[str], last_wins]
    reply_blocked: bool
