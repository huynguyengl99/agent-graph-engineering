from typing import Any, Literal

from pydantic import BaseModel

from ..shared.messages import (
    AnswerMessage,
    ApprovalRequiredMessage,
    ChatCompleteMessage,
    ChatErrorMessage,
    ChatTokenMessage,
    ClassifiedMessage,
    DecidedMessage,
    ModelOverrides,
    ReplayRequestMessage,
    ReplyBlockedMessage,
    ReplySentMessage,
    ToolApprovalMessage,
    ToolRanMessage,
    TriageErrorMessage,
)


class ChatTicket(BaseModel):
    """The ticket a conversation was opened about, when there is one."""

    ticket_id: str
    title: str
    description: str


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


class ToolDecisionPayload(BaseModel):
    """ToolDecisionPayload"""

    conversation_id: str
    approved: bool
    arguments: dict[str, Any] = {}


class ToolDecisionMessage(BaseModel):
    """Resume a run parked at the tool gate."""

    action: Literal["tool_decision"] = "tool_decision"
    payload: ToolDecisionPayload


IncomingMessage = (
    ClassifiedMessage
    | DecidedMessage
    | AnswerMessage
    | ApprovalRequiredMessage
    | ReplySentMessage
    | ReplyBlockedMessage
    | ChatTokenMessage
    | ChatCompleteMessage
    | ToolApprovalMessage
    | ToolRanMessage
    | TriageErrorMessage
    | ChatErrorMessage
)
OutgoingMessage = ChatRequestMessage | ReplayRequestMessage | ToolDecisionMessage
