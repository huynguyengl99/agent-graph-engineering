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
    # Public asks the agent to answer the customer; internal asks it a question
    # only the team will see.
    public: bool = False
    question: str = ""


class AskAgentMessage(BaseMessage):
    """Staff asks the agent to work this ticket."""

    action: Literal["ask_agent"] = "ask_agent"
    payload: AskAgentPayload


class SetAgentPayload(BaseModel):
    # On, the agent answers new customer messages; off, the team does.
    on: bool
    reason: str = ""


class SetAgentMessage(BaseMessage):
    """Staff turns the agent on this ticket on or off."""

    action: Literal["set_agent"] = "set_agent"
    payload: SetAgentPayload
