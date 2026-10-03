from typing import Annotated

from pydantic import BaseModel

from assistant.agents.deps import Context
from assistant.graphs.states.reducers import last_wins
from assistant.outputs.triage import TicketAnswer


class DeliveryState(BaseModel):
    """Everything between a drafted answer and the customer seeing it.

    Shares `context`, `answer` and the guard/receipt keys with the parent, which is
    what lets the compiled subgraph be a node. `answer` is required: a parent that
    reaches here without one is miswired.
    """

    context: Context
    answer: TicketAnswer

    guardrail_findings: Annotated[list[str], last_wins] = []
    reply_blocked: bool = False
    approval_granted: bool = False
    delivery_receipt: str = ""
    tool_error: str = ""
