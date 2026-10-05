"""The team's half of a ticket's feed, addressed as `ticket:<id>:team`.

A customer and a colleague watch the same ticket, so what each may see is
decided where a connection joins rather than on every event it would have been
sent. Nothing arrives here that a customer may read.
"""

from channels.db import database_sync_to_async

from chanx.core.topic import Topic

from helpdesk.tickets.messages import (
    AgentProgressMessage,
    ApprovalRequiredMessage,
    NewEventMessage,
    ReasoningDeltaMessage,
    ToolProposalMessage,
)
from helpdesk.tickets.models import Ticket

TeamFeedEvent = (
    NewEventMessage
    | AgentProgressMessage
    | ApprovalRequiredMessage
    | ToolProposalMessage
    | ReasoningDeltaMessage
)


class TicketTeamTopic(Topic[TeamFeedEvent]):
    """Outbound only: the actions a reviewer takes are sent on the ticket's own
    topic, which they are also subscribed to."""

    pattern = "ticket:{ticket_id}:team"
    passthrough_events = [
        NewEventMessage,
        AgentProgressMessage,
        ApprovalRequiredMessage,
        ToolProposalMessage,
        ReasoningDeltaMessage,
    ]

    async def authorize(self, **params: str) -> bool:
        user = self.scope.get("user")
        if not (user is not None and getattr(user, "is_staff", False)):
            return False
        return bool(await self._ticket_exists(params["ticket_id"]))

    @database_sync_to_async
    def _ticket_exists(self, ticket_id: str) -> bool:
        return Ticket.objects.filter(id=ticket_id).exists()
