from typing import Literal

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


class TriageRequestPayload(BaseModel):
    """TriageRequestPayload"""

    ticket_id: str
    title: str
    description: str
    history: list[str] = []
    models: ModelOverrides | None = None


class TriageRequestMessage(BaseModel):
    """Backend asks the agent to work a ticket."""

    action: Literal["triage_request"] = "triage_request"
    payload: TriageRequestPayload


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
OutgoingMessage = ApprovalDecisionMessage | ReplayRequestMessage | TriageRequestMessage
