"""What graphs share, declared once and mixed in where it is shared.

A subgraph composes into a parent by sharing state keys, so the keys they share
are a contract. Named mixins make it one: a parent that composes the tool
subgraph says so by carrying `Tools`, rather than by happening to spell the
same nine fields.
"""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, field_validator

from assistant.agents.deps import Context
from assistant.graphs.states.reducers import last_wins


class ToolRun(StrEnum):
    """How far a tool call has got, and the whole of how a resume routes.

    Nothing says "this run is a resume": `PENDING` means a person is holding
    it, and anything past that is their answer.
    """

    NOT_STARTED = "not_started"
    PENDING = "pending"
    APPROVED = "approved"
    CANCELLED = "cancelled"
    DONE = "done"


class ReplyRun(StrEnum):
    """The same, for a drafted reply on its way to a customer."""

    NOT_STARTED = "not_started"
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

    @field_validator("tool_run", mode="before")
    @classmethod
    def _tool_run_blank_is_unstarted(cls, value: Any) -> Any:
        """A blank is a run that has not got there yet.

        The member was spelled `""` until this state was stored, and a thread
        parked before then would otherwise fail to validate on its way back
        in, which is the whole thread lost rather than one stale field.
        """
        return value or ToolRun.NOT_STARTED


class Delivery(BaseModel):
    """Shared with the delivery subgraph: everything between a draft and a send."""

    # Set when the run is handing the ticket over. Shared because it changes
    # who reads the message first: a person has already been sent for.
    escalation_reason: str = ""
    guardrail_findings: Annotated[list[str], last_wins] = []
    reply_run: ReplyRun = ReplyRun.NOT_STARTED
    delivery_receipt: str = ""

    @field_validator("reply_run", mode="before")
    @classmethod
    def _reply_run_blank_is_unstarted(cls, value: Any) -> Any:
        """The same, for a state stored while `""` was the name."""
        return value or ReplyRun.NOT_STARTED


class Decision(BaseModel):
    """What a person answered, as the fields it sets on the next run.

    The answer has to arrive as a status, because a status is all the entry
    routers read. Spelling it as a model rather than loose keyword arguments
    is not ceremony: a state ignores a key it does not know, so a mistyped
    one used to leave `tool_run` at `pending`, and the run somebody had just
    approved would quietly park again.
    """

    model_config = ConfigDict(extra="forbid")

    tool_run: ToolRun | None = None
    reply_run: ReplyRun | None = None
    arguments: dict[str, Any] | None = None
    corrected: bool | None = None
    answer: dict[str, Any] | None = None

    def over(self, carried: dict[str, Any]) -> dict[str, Any]:
        """The carried state with the decision written onto it."""
        return {**carried, **self.model_dump(exclude_none=True)}
