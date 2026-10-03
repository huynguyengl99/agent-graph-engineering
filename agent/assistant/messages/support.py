"""What a support run is asked for, and what it emits, whoever its answer is for."""

from typing import Literal

from chanx.messages.base import BaseMessage
from pydantic import BaseModel

from assistant.messages.chat import (
    ChatCompleteMessage,
    ChatErrorMessage,
    ChatTokenMessage,
    ToolApprovalMessage,
    ToolRanMessage,
)
from assistant.messages.triage import (
    AnswerMessage,
    ApprovalRequiredMessage,
    ClassifiedMessage,
    DecidedMessage,
    ModelOverrides,
    ReplyBlockedMessage,
    ReplySentMessage,
    TriageErrorMessage,
)

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
)


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
