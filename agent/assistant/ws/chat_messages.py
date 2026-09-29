from typing import Literal

from chanx.messages.base import BaseMessage
from pydantic import BaseModel


class ChatTicket(BaseModel):
    """The ticket a conversation was opened about, when there is one."""

    ticket_id: str
    title: str
    description: str


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequestPayload(BaseModel):
    conversation_id: str
    question: str
    history: list[ChatTurn] = []
    ticket: ChatTicket | None = None


class ChatRequestMessage(BaseMessage):
    """A support agent asks the assistant something."""

    action: Literal["chat_request"] = "chat_request"
    payload: ChatRequestPayload


class ChatTokenPayload(BaseModel):
    conversation_id: str
    delta: str


class ChatTokenMessage(BaseMessage):
    """One delta of the answer, forwarded as the graph produces it."""

    action: Literal["chat_token"] = "chat_token"
    payload: ChatTokenPayload


class ChatCompletePayload(BaseModel):
    conversation_id: str
    content: str


class ChatCompleteMessage(BaseMessage):
    """The finished answer, for persistence."""

    action: Literal["chat_complete"] = "chat_complete"
    payload: ChatCompletePayload


class ChatErrorPayload(BaseModel):
    conversation_id: str
    message: str


class ChatErrorMessage(BaseMessage):
    action: Literal["chat_error"] = "chat_error"
    payload: ChatErrorPayload
