"""Where an event on a ticket goes, derived from the event itself.

Nothing chooses an audience at a call site: a message type that is the team's
goes to the team's topic, and one the customer may read goes to the ticket's.
A new message type has to say which, because there is no default.
"""

from chanx.messages.base import BaseMessage

from helpdesk.tickets.messages import (
    AgentProgressMessage,
    AnswerStreamingMessage,
    ApprovalRequiredMessage,
    NewEventMessage,
    ReasoningDeltaMessage,
    ToolProposalMessage,
)
from helpdesk.tickets.messages.events import HandoffEvent, TicketEvent, ToolCallEvent

TEAM_ONLY: tuple[type[BaseMessage], ...] = (
    AgentProgressMessage,
    ApprovalRequiredMessage,
    ToolProposalMessage,
    ReasoningDeltaMessage,
)


def ticket_topic(ticket_id: str) -> str:
    return f"ticket:{ticket_id}"


def team_topic(ticket_id: str) -> str:
    return f"ticket:{ticket_id}:team"


def for_customer(event: TicketEvent) -> TicketEvent | None:
    """The customer's view of an event, or nothing when it is not theirs.

    Visible is not readable: they are told a person took over, not why, and
    that a tool ran, not what it was handed.
    """
    if event.visibility != "public":
        return None
    match event:
        case HandoffEvent():
            return event.model_copy(update={"reason": ""})
        case ToolCallEvent():
            return event.model_copy(update={"arguments": {}, "result": "", "error": ""})
        case _:
            return event


async def publish(ticket_id: str, message: BaseMessage) -> None:
    """Send one event to whichever audiences it belongs to."""
    # Imported here: a topic sends through this, so it cannot be imported at
    # the top of a module the topics import.
    from helpdesk.tickets.topics.team_topic import TicketTeamTopic
    from helpdesk.tickets.topics.ticket_topic import TicketTopic

    if isinstance(message, TEAM_ONLY):
        await TicketTeamTopic.broadcast(team_topic(ticket_id), message)
        return

    # The reply as it is written goes where the finished reply will go, so the
    # customer never watches a draft that turns out to be the team's.
    if isinstance(message, AnswerStreamingMessage):
        await TicketTeamTopic.broadcast(team_topic(ticket_id), message)
        if message.payload.public:
            await TicketTopic.broadcast(ticket_topic(ticket_id), message)
        return

    if not isinstance(message, NewEventMessage):
        await TicketTopic.broadcast(ticket_topic(ticket_id), message)
        return

    # The team sees the whole event; the customer sees their view of it, and
    # only when it is theirs at all.
    await TicketTeamTopic.broadcast(team_topic(ticket_id), message)
    if (theirs := for_customer(message.payload.event)) is not None:
        await TicketTopic.broadcast(
            ticket_topic(ticket_id),
            message.model_copy(
                update={"payload": message.payload.model_copy(update={"event": theirs})}
            ),
        )
