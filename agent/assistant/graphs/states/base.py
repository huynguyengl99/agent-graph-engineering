"""What graphs share, declared once and mixed in where it is shared.

A subgraph composes into a parent by sharing state keys, so the keys they share
are a contract. Named mixins make it one: a parent that composes the tool
subgraph says so by carrying `Tools`, rather than by happening to spell the
same nine fields.
"""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel

from assistant.agents.deps import Context
from assistant.graphs.states.reducers import last_wins


class ToolRun(StrEnum):
    """How far a tool call has got, and the whole of how a resume routes.

    Nothing says "this run is a resume": `PENDING` means a person is holding
    it, and anything past that is their answer.
    """

    NOT_STARTED = ""
    PENDING = "pending"
    APPROVED = "approved"
    CANCELLED = "cancelled"
    DONE = "done"


class ReplyRun(StrEnum):
    """The same, for a drafted reply on its way to a customer."""

    NOT_STARTED = ""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    BLOCKED = "blocked"


class BaseState(BaseModel):
    """Every graph is handed what the run is about."""

    context: Context


class Knowledge(BaseModel):
    """Shared with the retrieval subgraph. Its own bookkeeping stays inside it."""

    kb_query: str = ""
    kb_snippets: Annotated[list[str], last_wins] = []


class Tools(BaseModel):
    """Shared with the tool subgraph: the proposal, the correction, the outcome."""

    request: str = ""
    tool: str = ""
    arguments: Annotated[dict[str, Any], last_wins] = {}
    unknown_arguments: list[str] = []
    tool_run: ToolRun = ToolRun.NOT_STARTED
    corrected: bool = False
    result: str = ""
    tool_error: str = ""


class Delivery(BaseModel):
    """Shared with the delivery subgraph: everything between a draft and a send."""

    # Set when the run is handing the ticket over. Shared because it changes
    # who reads the message first: a person has already been sent for.
    escalation_reason: str = ""
    guardrail_findings: Annotated[list[str], last_wins] = []
    reply_run: ReplyRun = ReplyRun.NOT_STARTED
    delivery_receipt: str = ""
