from typing import Any, Literal

from pydantic import BaseModel

from ..shared.messages import ModelOverrides, ReplayRequestMessage


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


class ToolApprovalPayload(BaseModel):
    """ToolApprovalPayload"""

    conversation_id: str
    tool: str
    description: str
    arguments: dict[str, Any] = {}
    arguments_schema: dict[str, Any] = {}
    unknown_arguments: list[str] = []


class ToolApprovalMessage(BaseModel):
    """A tool is waiting on a human. Nothing has run."""

    action: Literal["tool_approval"] = "tool_approval"
    payload: ToolApprovalPayload


class ToolDecisionPayload(BaseModel):
    """ToolDecisionPayload"""

    conversation_id: str
    approved: bool
    arguments: dict[str, Any] = {}


class ToolDecisionMessage(BaseModel):
    """Resume a run parked at the tool gate."""

    action: Literal["tool_decision"] = "tool_decision"
    payload: ToolDecisionPayload


class ToolRanPayload(BaseModel):
    """ToolRanPayload"""

    conversation_id: str
    tool: str
    arguments: dict[str, Any] = {}
    result: str = ""
    error: str = ""
    cancelled: bool = False


class ToolRanMessage(BaseModel):
    """What a tool did, once it has done it."""

    action: Literal["tool_ran"] = "tool_ran"
    payload: ToolRanPayload


IncomingMessage = (
    ChatTokenMessage
    | ChatCompleteMessage
    | ToolApprovalMessage
    | ToolRanMessage
    | ChatErrorMessage
)
OutgoingMessage = ChatRequestMessage | ReplayRequestMessage | ToolDecisionMessage
