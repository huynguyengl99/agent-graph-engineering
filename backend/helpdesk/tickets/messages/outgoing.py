from typing import Any, Literal

from chanx.messages.base import BaseMessage
from pydantic import BaseModel

from helpdesk.tickets.messages.events import TicketEvent


class NewEventPayload(BaseModel):
    """A polymorphic `TicketEvent`, discriminated by `eventType`."""

    event: TicketEvent


class NewEventMessage(BaseMessage):
    action: Literal["new_event"] = "new_event"
    payload: NewEventPayload


class StreamingPayload(BaseModel):
    chunk: str


class StreamingMessage(BaseMessage):
    """One delta of an in-progress agent answer."""

    action: Literal["streaming"] = "streaming"
    payload: StreamingPayload


class CompleteStreamingPayload(BaseModel):
    event: TicketEvent


class CompleteStreamingMessage(BaseMessage):
    """Streaming finished; carries the persisted `AIResponseEvent`."""

    action: Literal["complete_streaming"] = "complete_streaming"
    payload: CompleteStreamingPayload


class AgentProgressPayload(BaseModel):
    stage: Literal["classified", "decided", "failed"]
    detail: str


class AgentProgressMessage(BaseMessage):
    """Progress while a run works, so the UI is not silent."""

    action: Literal["agent_progress"] = "agent_progress"
    payload: AgentProgressPayload


class ApprovalRequiredPayload(BaseModel):
    draft: str
    # What the output guard noticed, so the reviewer starts informed.
    findings: list[str] = []


class ApprovalRequiredMessage(BaseMessage):
    """The agent has parked on a reply and is waiting for a human."""

    action: Literal["approval_required"] = "approval_required"
    payload: ApprovalRequiredPayload


class ToolProposalPayload(BaseModel):
    """A tool is waiting on this ticket. Nothing has run yet."""

    tool: str
    description: str
    arguments: dict[str, Any] = {}
    # JSON Schema for the arguments; the correction form is generated from it.
    arguments_schema: dict[str, Any] = {}
    unknown_arguments: list[str] = []


class ToolProposalMessage(BaseMessage):
    action: Literal["tool_proposal"] = "tool_proposal"
    payload: ToolProposalPayload


class AgentWorkingPayload(BaseModel):
    """Whether the assistant is working on this ticket right now.

    One per run, from the moment it is picked up to the moment it lets go, so
    a thread is never quietly busy. The team see it for either lane; the
    customer only for the run that is about answering them.
    """

    working: bool
    public: bool = True


class AgentWorkingMessage(BaseMessage):
    action: Literal["agent_working"] = "agent_working"
    payload: AgentWorkingPayload


class TicketUpdatedPayload(BaseModel):
    status: str
    priority: str


class TicketUpdatedMessage(BaseMessage):
    """The ticket's own fields, after something changed them."""

    action: Literal["ticket_updated"] = "ticket_updated"
    payload: TicketUpdatedPayload


class ReasoningStreamingPayload(BaseModel):
    """The agent's reasoning for one step, as far as it has been written.

    Whole each time rather than the piece just added, for the same reason as
    the reply: a late subscriber sees all of it, and a dropped frame is put
    right by the next one instead of losing a word in the middle.
    """

    reference: str
    step: str = ""
    content: str
    public: bool


class ReasoningStreamingMessage(BaseMessage):
    action: Literal["reasoning_streaming"] = "reasoning_streaming"
    payload: ReasoningStreamingPayload


class AnswerStreamingPayload(BaseModel):
    """The reply as far as it has been written.

    The whole of it each time, not the piece just added: a subscriber that
    joins late, or misses a frame, still renders what the agent has said. The
    reference is stable for one answer, so a client replaces rather than
    appends, and drops it when the event carrying the finished reply arrives.
    """

    reference: str
    content: str
    public: bool


class AnswerStreamingMessage(BaseMessage):
    action: Literal["answer_streaming"] = "answer_streaming"
    payload: AnswerStreamingPayload
