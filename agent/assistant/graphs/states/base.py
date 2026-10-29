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


class Resuming(StrEnum):
    """Which pause this run is picking up, if any.

    A run ends at a gate rather than suspending inside it, so resuming is a
    new run carrying the state the last one finished with. This says which
    entry it should take instead of starting from the top.
    """

    NOTHING = ""
    TOOL_APPROVAL = "tool_approval"
    REPLY_APPROVAL = "reply_approval"


class BaseState(BaseModel):
    """Every graph is handed what the run is about."""

    context: Context
    # Set by the backend when it sends a reviewer's answer back, read by the
    # entry router of whichever graph owns that gate.
    resuming: Resuming = Resuming.NOTHING
    # Set by a gate on its way out, so the caller knows the run stopped for a
    # person rather than finishing.
    awaiting: Resuming = Resuming.NOTHING


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
    approved: bool = False
    corrected: bool = False
    cancelled: bool = False
    result: str = ""
    tool_error: str = ""


class Delivery(BaseModel):
    """Shared with the delivery subgraph: everything between a draft and a send."""

    # Set when the run is handing the ticket over. Shared because it changes
    # who reads the message first: a person has already been sent for.
    escalation_reason: str = ""
    guardrail_findings: Annotated[list[str], last_wins] = []
    reply_blocked: bool = False
    approval_granted: bool = False
    delivery_receipt: str = ""
