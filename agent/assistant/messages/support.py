"""The events a support run emits, whoever its answer is for."""

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
