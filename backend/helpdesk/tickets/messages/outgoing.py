from typing import Literal

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
