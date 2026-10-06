"""The ticket event union, as it travels over the WebSocket.

These mirror the polymorphic `TicketEvent` serializers. Declaring them properly
rather than as `dict[str, Any]` is what lets the AsyncAPI document carry a
discriminated union, so the generated client narrows on `eventType` exactly as
the REST client does. Typed everywhere except the realtime boundary would be a
strange place to give up.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class EventUser(BaseModel):
    id: str
    email: str
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    date_joined: str = ""


class BaseEvent(BaseModel):
    id: int
    created_by: EventUser | None = None
    # Who the event is for. The composer and the badge read this.
    visibility: Literal["internal", "public"] = "internal"
    created_at: str


class CommentEvent(BaseEvent):
    event_type: Literal["comment"] = "comment"
    content: str


class StatusChangeEvent(BaseEvent):
    event_type: Literal["status_change"] = "status_change"
    old_status: str
    new_status: str


class AIResponseEvent(BaseEvent):
    event_type: Literal["ai_response"] = "ai_response"
    content: str
    model_name: str = ""
    tokens_used: int = 0


class HandoffEvent(BaseEvent):
    event_type: Literal["handoff"] = "handoff"
    handling: Literal["agent", "needs_human", "with_staff"]
    reason: str = ""


class ReasoningEvent(BaseEvent):
    event_type: Literal["reasoning"] = "reasoning"
    step: str = ""
    content: str
    decision: str = ""
    model_name: str = ""


class ToolCallEvent(BaseEvent):
    event_type: Literal["tool_call"] = "tool_call"
    tool: str
    arguments: dict[str, Any] = {}
    result: str = ""
    error: str = ""
    cancelled: bool = False


TicketEvent = Annotated[
    CommentEvent
    | StatusChangeEvent
    | AIResponseEvent
    | HandoffEvent
    | ToolCallEvent
    | ReasoningEvent,
    Field(discriminator="event_type"),
]
