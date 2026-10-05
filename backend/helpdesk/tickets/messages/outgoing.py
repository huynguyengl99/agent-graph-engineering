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
    """Intermediate triage progress, so the UI is not silent while it works."""

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

    Deliberately a boolean and nothing else. Which step it is on, what it
    decided and what it is reading are the team's; that someone is dealing
    with your ticket is the customer's, and without it they watch an empty
    thread and wonder whether anything was received.
    """

    working: bool


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


class ReasoningDeltaPayload(BaseModel):
    """A piece of the agent's reasoning, as it is written. Staff only."""

    step: str = ""
    delta: str


class ReasoningDeltaMessage(BaseMessage):
    action: Literal["reasoning_delta"] = "reasoning_delta"
    payload: ReasoningDeltaPayload
