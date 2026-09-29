from typing import Annotated, TypedDict

from assistant.agents.deps import TicketContext
from assistant.outputs.triage import TicketAnswer


def last_wins(_current: object, incoming: object) -> object:
    return incoming


class DeliveryState(TypedDict, total=False):
    """Everything between a drafted answer and the customer seeing it.

    Shares `context`, `answer` and the guard/receipt keys with the parent,
    which is what lets the compiled subgraph be added as a node.
    """

    context: TicketContext
    answer: TicketAnswer

    guardrail_findings: Annotated[list[str], last_wins]
    reply_blocked: bool
    approval_granted: bool
    delivery_receipt: str
    tool_error: str
