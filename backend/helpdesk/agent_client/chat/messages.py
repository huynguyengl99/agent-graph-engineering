from typing import Literal

from pydantic import BaseModel

from ..shared.messages import ModelOverrides, PingMessage, PongMessage


class ChatCompletePayload(BaseModel):
    """ChatCompletePayload"""

    conversation_id: str
    content: str


class ChatCompleteMessage(BaseModel):
    """The finished answer, for persistence."""

    action: Literal["chat_complete"] = "chat_complete"
    payload: ChatCompletePayload


class ChatErrorPayload(BaseModel):
    """ChatErrorPayload"""

    conversation_id: str
    message: str


class ChatErrorMessage(BaseModel):
    """ChatErrorMessage"""

    action: Literal["chat_error"] = "chat_error"
    payload: ChatErrorPayload


class ChatTicket(BaseModel):
    """The ticket a conversation was opened about, when there is one."""

    ticket_id: str
    title: str
    description: str


class ChatTokenPayload(BaseModel):
    """ChatTokenPayload"""

    conversation_id: str
    delta: str


class ChatTokenMessage(BaseModel):
    """One delta of the answer, forwarded as the graph produces it."""

    action: Literal["chat_token"] = "chat_token"
    payload: ChatTokenPayload


class ChatTurn(BaseModel):
    """ChatTurn"""

    role: Literal["user", "assistant"]
    content: str


class ChatRequestPayload(BaseModel):
    """ChatRequestPayload"""

    conversation_id: str
    question: str
    history: list[ChatTurn] = []
    ticket: ChatTicket | None = None
    models: ModelOverrides | None = None


class ChatRequestMessage(BaseModel):
    """A support agent asks the assistant something."""

    action: Literal["chat_request"] = "chat_request"
    payload: ChatRequestPayload


IncomingMessage = (
    ChatTokenMessage | ChatCompleteMessage | ChatErrorMessage | PongMessage
)
OutgoingMessage = ChatRequestMessage | PingMessage
