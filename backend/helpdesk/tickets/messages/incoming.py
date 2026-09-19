from typing import Literal

from chanx.messages.base import BaseMessage
from pydantic import BaseModel


class SendMessagePayload(BaseModel):
    content: str


class SendMessageMessage(BaseMessage):
    """A human posts a comment on the ticket."""

    action: Literal["send_message"] = "send_message"
    payload: SendMessagePayload


class ApprovalDecisionPayload(BaseModel):
    approved: bool
    content: str | None = None


class ApprovalDecisionMessage(BaseMessage):
    """A reviewer accepts, edits, or rejects the drafted reply."""

    action: Literal["approval_decision"] = "approval_decision"
    payload: ApprovalDecisionPayload
