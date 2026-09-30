from typing import Any, Literal

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


class ToolApprovalPayload(BaseModel):
    """A tool is waiting on this rep. Nothing has run yet."""

    tool: str
    description: str
    arguments: dict[str, Any] = {}
    # JSON Schema for the arguments. The correction form is generated from it,
    # so adding a tool to the agent needs no change in the browser.
    arguments_schema: dict[str, Any] = {}
    # Argument names the planner made up. Already dropped by the agent; shown
    # so an empty required field on the form has an explanation.
    unknown_arguments: list[str] = []


class ToolApprovalMessage(BaseMessage):
    """Relayed from the agent's gate, unchanged apart from the ids."""

    action: Literal["tool_approval"] = "tool_approval"
    payload: ToolApprovalPayload


class ChatErrorPayload(BaseModel):
    detail: str


class ChatErrorMessage(BaseMessage):
    action: Literal["chat_error"] = "chat_error"
    payload: ChatErrorPayload
