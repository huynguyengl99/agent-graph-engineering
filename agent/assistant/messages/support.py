"""The agent's wire contract: what a run is asked for, and what it emits.

One module because there is one graph. It was two - a ticket's and a
conversation's - and the generator produced two clients that each knew half of
what a run does.
"""

from typing import Any, Literal

from chanx.messages.base import BaseMessage
from pydantic import BaseModel

from assistant.outputs.support import Category, Priority


class ModelOverrides(BaseModel):
    """Which model fills each purpose for this run.

    The caller may set any subset; unset purposes fall through to the
    deployment default. It cannot change *which* purpose a step runs under,
    which is what keeps routing off the wrong class of model.
    """

    decision: str | None = None
    answer: str | None = None


class TriageRequestPayload(BaseModel):
    ticket_id: str
    title: str
    description: str
    history: list[str] = []
    models: ModelOverrides | None = None


class TriageRequestMessage(BaseMessage):
    """Backend asks the agent to work a ticket."""

    action: Literal["triage_request"] = "triage_request"
    payload: TriageRequestPayload


class ClassifiedPayload(BaseModel):
    ticket_id: str
    category: Category
    priority: Priority
    reasoning: str


class ClassifiedMessage(BaseMessage):
    """Emitted as soon as the ticket is filed, before any answer exists."""

    action: Literal["classified"] = "classified"
    payload: ClassifiedPayload


class DecidedPayload(BaseModel):
    ticket_id: str
    decision: str
    reasoning: str


class DecidedMessage(BaseMessage):
    """Which branch of the graph the agent took."""

    action: Literal["decided"] = "decided"
    payload: DecidedPayload


class AnswerPayload(BaseModel):
    ticket_id: str
    content: str
    requires_approval: bool


class AnswerMessage(BaseMessage):
    """The agent's proposed reply."""

    action: Literal["answer"] = "answer"
    payload: AnswerPayload


class TriageErrorPayload(BaseModel):
    ticket_id: str
    message: str


class TriageErrorMessage(BaseMessage):
    action: Literal["triage_error"] = "triage_error"
    payload: TriageErrorPayload


class ApprovalRequiredPayload(BaseModel):
    ticket_id: str
    draft: str
    # What the machine guard noticed, so the reviewer starts informed.
    findings: list[str] = []


class ApprovalRequiredMessage(BaseMessage):
    """The graph is paused, waiting on a human."""

    action: Literal["approval_required"] = "approval_required"
    payload: ApprovalRequiredPayload


class ReplyBlockedPayload(BaseModel):
    ticket_id: str
    draft: str
    findings: list[str]


class ReplyBlockedMessage(BaseMessage):
    """The output guard stopped the draft before a human was asked."""

    action: Literal["reply_blocked"] = "reply_blocked"
    payload: ReplyBlockedPayload


class ApprovalDecisionPayload(BaseModel):
    ticket_id: str
    approved: bool
    content: str | None = None
    # Carried on the resume too, so a run does not change models halfway
    # through. Nothing after the gate calls a model today, but that is a
    # property of the current graph, not something to rely on.
    models: ModelOverrides | None = None


class ApprovalDecisionMessage(BaseMessage):
    """Resume a paused run. `content` overrides the draft when edited."""

    action: Literal["approval_decision"] = "approval_decision"
    payload: ApprovalDecisionPayload


class ReplySentPayload(BaseModel):
    ticket_id: str
    receipt: str


class ReplySentMessage(BaseMessage):
    action: Literal["reply_sent"] = "reply_sent"
    payload: ReplySentPayload


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


class TicketRef(BaseModel):
    """The ticket a run is about. Absent for a question with no ticket behind it."""

    ticket_id: str
    title: str
    description: str


class RunTurn(BaseModel):
    """One thing already said on the thread."""

    role: str
    content: str


class RunRequestPayload(BaseModel):
    """One message to work.

    The audience rides the topic rather than the payload: a customer's run and
    the team's run about one ticket are different threads, and keying them apart
    is what stops one resuming into the other.
    """

    # Empty for a customer's run: the ticket is the question.
    question: str = ""
    ticket: TicketRef | None = None
    history: list[RunTurn] = []
    models: ModelOverrides | None = None


class RunRequestMessage(BaseMessage):
    """Work this message."""

    action: Literal["run_request"] = "run_request"
    payload: RunRequestPayload


class ReasoningDeltaPayload(BaseModel):
    thread_id: str
    step: str = ""
    delta: str


class ReasoningDeltaMessage(BaseMessage):
    """A piece of the model's reasoning, as it is written."""

    action: Literal["reasoning_delta"] = "reasoning_delta"
    payload: ReasoningDeltaPayload


class ReasonedPayload(BaseModel):
    thread_id: str
    # Which step explained itself: a run has several that do.
    step: str = ""
    content: str
    decision: str
    model: str = ""


class ReasonedMessage(BaseMessage):
    """The finished reasoning, for the record."""

    action: Literal["reasoned"] = "reasoned"
    payload: ReasonedPayload


# One graph, so one set of events: a topic that declared only half of them
# dropped the other half with a validation error nobody was watching for.
SupportEvent = (
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
    | ReasoningDeltaMessage
    | ReasonedMessage
)
