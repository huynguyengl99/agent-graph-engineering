from typing import Literal

from chanx.messages.base import BaseMessage
from pydantic import BaseModel


class ChatMessagePayload(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str


class ChatMessageMessage(BaseMessage):
    """A persisted turn, echoed to every tab on this conversation."""

    action: Literal["chat_message"] = "chat_message"
    payload: ChatMessagePayload


class TokenPayload(BaseModel):
    """No id: there is only ever one answer streaming per conversation, and it
    has no database row until it finishes."""

    delta: str


class TokenMessage(BaseMessage):
    """One delta of the assistant's answer, as it is produced."""

    action: Literal["token"] = "token"
    payload: TokenPayload


class AssistantDonePayload(BaseModel):
    message_id: str
    content: str


class AssistantDoneMessage(BaseMessage):
    """Streaming finished; carries the final persisted text."""

    action: Literal["assistant_done"] = "assistant_done"
    payload: AssistantDonePayload


class ChatErrorPayload(BaseModel):
    detail: str


class ChatErrorMessage(BaseMessage):
    action: Literal["chat_error"] = "chat_error"
    payload: ChatErrorPayload
