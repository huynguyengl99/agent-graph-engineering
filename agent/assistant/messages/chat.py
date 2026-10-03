from typing import Any, Literal

from chanx.messages.base import BaseMessage
from pydantic import BaseModel

from assistant.messages.triage import ModelOverrides


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
    models: ModelOverrides | None = None


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


class ToolApprovalPayload(BaseModel):
    conversation_id: str
    tool: str
    description: str
    arguments: dict[str, Any] = {}
    # JSON Schema for the arguments. The reviewer's form is generated from
    # this, so the UI needs to know nothing about any particular tool. Named in
    # full because a bare `schema` shadows a BaseModel attribute, and the
    # generated clients inherit the field name.
    arguments_schema: dict[str, Any] = {}
    # Names the planner passed that the tool does not take. They have been
    # dropped, and the reviewer is shown them so an empty required field has an
    # explanation instead of looking like a bug.
    unknown_arguments: list[str] = []


class ToolApprovalMessage(BaseMessage):
    """A tool is waiting on a human. Nothing has run."""

    action: Literal["tool_approval"] = "tool_approval"
    payload: ToolApprovalPayload


class ToolDecisionPayload(BaseModel):
    conversation_id: str
    approved: bool
    # Corrected arguments, when the reviewer changed them. Empty means run
    # what was proposed.
    arguments: dict[str, Any] = {}


class ToolDecisionMessage(BaseMessage):
    """Resume a run parked at the tool gate."""

    action: Literal["tool_decision"] = "tool_decision"
    payload: ToolDecisionPayload


class ToolRanPayload(BaseModel):
    conversation_id: str
    tool: str
    # What ran, which is the proposal plus whatever the reviewer corrected.
    arguments: dict[str, Any] = {}
    result: str = ""
    error: str = ""
    cancelled: bool = False


class ToolRanMessage(BaseMessage):
    """What a tool did, once it has done it."""

    action: Literal["tool_ran"] = "tool_ran"
    payload: ToolRanPayload


class ChatErrorPayload(BaseModel):
    conversation_id: str
    message: str


class ChatErrorMessage(BaseMessage):
    action: Literal["chat_error"] = "chat_error"
    payload: ChatErrorPayload
