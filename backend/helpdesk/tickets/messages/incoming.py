from typing import Literal

from chanx.messages.base import BaseMessage
from pydantic import BaseModel


class SendMessagePayload(BaseModel):
    content: str
    # Staff choose; the requester's own message is public whatever this says.
    public: bool = False


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


class AskAgentPayload(BaseModel):
    # Public asks the agent to answer the customer; internal keeps it a draft.
    public: bool = False


class AskAgentMessage(BaseMessage):
    """Staff asks the agent to work this ticket."""

    action: Literal["ask_agent"] = "ask_agent"
    payload: AskAgentPayload


class ReturnToAgentPayload(BaseModel):
    reason: str = ""


class ReturnToAgentMessage(BaseMessage):
    """Staff gives the ticket back to the agent."""

    action: Literal["return_to_agent"] = "return_to_agent"
    payload: ReturnToAgentPayload
