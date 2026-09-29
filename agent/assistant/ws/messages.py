from typing import Literal

from chanx.messages.base import BaseMessage
from pydantic import BaseModel

from assistant.outputs.triage import Category, Priority


class TriageRequestPayload(BaseModel):
    ticket_id: str
    title: str
    description: str
    history: list[str] = []


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
