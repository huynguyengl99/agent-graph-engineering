from typing import Literal

from pydantic import BaseModel

from ..shared.messages import PingMessage, PongMessage


class AnswerPayload(BaseModel):
    """AnswerPayload"""

    ticket_id: str
    content: str
    requires_approval: bool


class AnswerMessage(BaseModel):
    """The agent's proposed reply."""

    action: Literal["answer"] = "answer"
    payload: AnswerPayload


class ApprovalDecisionPayload(BaseModel):
    """ApprovalDecisionPayload"""

    ticket_id: str
    approved: bool
    content: str | None = None


class ApprovalDecisionMessage(BaseModel):
    """Resume a paused run. `content` overrides the draft when edited."""

    action: Literal["approval_decision"] = "approval_decision"
    payload: ApprovalDecisionPayload


class ApprovalRequiredPayload(BaseModel):
    """ApprovalRequiredPayload"""

    ticket_id: str
    draft: str
    findings: list[str] = []


class ApprovalRequiredMessage(BaseModel):
    """The graph is paused, waiting on a human."""

    action: Literal["approval_required"] = "approval_required"
    payload: ApprovalRequiredPayload


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


class TriageErrorPayload(BaseModel):
    """TriageErrorPayload"""

    ticket_id: str
    message: str


class TriageErrorMessage(BaseModel):
    """TriageErrorMessage"""

    action: Literal["triage_error"] = "triage_error"
    payload: TriageErrorPayload


class TriageRequestPayload(BaseModel):
    """TriageRequestPayload"""

    ticket_id: str
    title: str
    description: str
    history: list[str] = []


class TriageRequestMessage(BaseModel):
    """Backend asks the agent to work a ticket."""

    action: Literal["triage_request"] = "triage_request"
    payload: TriageRequestPayload


IncomingMessage = (
    ReplySentMessage
    | AnswerMessage
    | TriageErrorMessage
    | PongMessage
    | ClassifiedMessage
    | DecidedMessage
    | ApprovalRequiredMessage
    | ReplyBlockedMessage
)
OutgoingMessage = ApprovalDecisionMessage | PingMessage | TriageRequestMessage
