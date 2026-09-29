from typing import Literal

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
