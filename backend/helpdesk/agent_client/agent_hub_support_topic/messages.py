from typing import Any, Literal

from pydantic import BaseModel


class AnswerPayload(BaseModel):
    """AnswerPayload"""

    ticket_id: str
    content: str
    requires_approval: bool


class AnswerMessage(BaseModel):
    """The agent's proposed reply."""

    action: Literal["answer"] = "answer"
    payload: AnswerPayload


class ApprovalRequiredPayload(BaseModel):
    """ApprovalRequiredPayload"""

    ticket_id: str
    draft: str
    findings: list[str] = []


class ApprovalRequiredMessage(BaseModel):
    """The graph is paused, waiting on a human."""

    action: Literal["approval_required"] = "approval_required"
    payload: ApprovalRequiredPayload


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


class ChatTokenPayload(BaseModel):
    """ChatTokenPayload"""

    conversation_id: str
    delta: str


class ChatTokenMessage(BaseModel):
    """One delta of the answer, forwarded as the graph produces it."""

    action: Literal["chat_token"] = "chat_token"
    payload: ChatTokenPayload


class ClassifiedPayload(BaseModel):
    """ClassifiedPayload"""

    ticket_id: str
    category: Literal["technical", "billing", "account", "general"]
    priority: Literal["low", "medium", "high", "urgent"]
    reasoning: str


class ClassifiedMessage(BaseModel):
    """Emitted as soon as the ticket is filed, before any answer exists."""

    action: Literal["classified"] = "classified"
    payload: ClassifiedPayload


class DecidedPayload(BaseModel):
    """DecidedPayload"""

    ticket_id: str
    decision: str
    reasoning: str


class DecidedMessage(BaseModel):
    """Which branch of the graph the agent took."""

    action: Literal["decided"] = "decided"
    payload: DecidedPayload


class ModelOverrides(BaseModel):
    """Which model fills each purpose for this run.

    The caller may set any subset; unset purposes fall through to the
    deployment default. It cannot change *which* purpose a step runs under,
    which is what keeps routing off the wrong class of model."""

    decision: str | None = None
    answer: str | None = None


class ApprovalDecisionPayload(BaseModel):
    """ApprovalDecisionPayload"""

    ticket_id: str
    approved: bool
    content: str | None = None
    models: ModelOverrides | None = None


class ApprovalDecisionMessage(BaseModel):
    """Resume a paused run. `content` overrides the draft when edited."""

    action: Literal["approval_decision"] = "approval_decision"
    payload: ApprovalDecisionPayload


class ReplayRequestPayload(BaseModel):
    """ReplayRequestPayload"""

    since: int = 0


class ReplayRequestMessage(BaseModel):
    """Subscriber reconnected and wants the events it was not there for.

    Answered on the asking connection only, in order, each carrying its original
    sequence - so a caller that applies them cannot tell a replay from the first
    time, except that it asked."""

    action: Literal["replay_request"] = "replay_request"
    payload: ReplayRequestPayload


class ReplyBlockedPayload(BaseModel):
    """ReplyBlockedPayload"""

    ticket_id: str
    draft: str
    findings: list[str]


class ReplyBlockedMessage(BaseModel):
    """The output guard stopped the draft before a human was asked."""

    action: Literal["reply_blocked"] = "reply_blocked"
    payload: ReplyBlockedPayload


class ReplySentPayload(BaseModel):
    """ReplySentPayload"""

    ticket_id: str
    receipt: str


class ReplySentMessage(BaseModel):
    """ReplySentMessage"""

    action: Literal["reply_sent"] = "reply_sent"
    payload: ReplySentPayload


class RunTurn(BaseModel):
    """One thing already said on the thread."""

    role: str
    content: str


class TicketRef(BaseModel):
    """The ticket a run is about. Absent for a question with no ticket behind it."""

    ticket_id: str
    title: str
    description: str


class RunRequestPayload(BaseModel):
    """One message to work.

    The audience rides the topic rather than the payload: a customer's run and
    the team's run about one ticket are different threads, and keying them apart
    is what stops one resuming into the other."""

    question: str = ""
    ticket: TicketRef | None = None
    history: list[RunTurn] = []
    models: ModelOverrides | None = None


class RunRequestMessage(BaseModel):
    """Work this message."""

    action: Literal["run_request"] = "run_request"
    payload: RunRequestPayload


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


class TriageErrorPayload(BaseModel):
    """TriageErrorPayload"""

    ticket_id: str
    message: str


class TriageErrorMessage(BaseModel):
    """TriageErrorMessage"""

    action: Literal["triage_error"] = "triage_error"
    payload: TriageErrorPayload


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
OutgoingMessage = (
    ApprovalDecisionMessage
    | ReplayRequestMessage
    | RunRequestMessage
    | ToolDecisionMessage
)
