from typing import Any, Literal

from chanx.messages.base import BaseMessage
from pydantic import BaseModel


class AskPayload(BaseModel):
    content: str


class AskMessage(BaseMessage):
    """A rep says something to the assistant."""

    action: Literal["ask"] = "ask"
    payload: AskPayload


class DraftToTicketPayload(BaseModel):
    ticket_id: str
    content: str


class DraftToTicketMessage(BaseMessage):
    """Hand a drafted reply over to a ticket, where approval applies."""

    action: Literal["draft_to_ticket"] = "draft_to_ticket"
    payload: DraftToTicketPayload


class ToolDecisionPayload(BaseModel):
    """What the reviewer did with a proposed tool call.

    `arguments` carries only the fields they changed, merged over the proposal
    by the caller. Empty means run it as proposed.
    """

    approved: bool
    arguments: dict[str, Any] = {}


class ToolDecisionMessage(BaseMessage):
    """Approve, correct, or cancel a tool the assistant proposed."""

    action: Literal["tool_decision"] = "tool_decision"
    payload: ToolDecisionPayload
