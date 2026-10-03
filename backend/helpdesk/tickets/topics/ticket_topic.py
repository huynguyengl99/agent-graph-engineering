from typing import Any

from channels.db import database_sync_to_async
from django.conf import settings

from chanx.core.decorators import event_handler, ws_handler
from chanx.core.topic import Topic

from helpdesk.tickets.messages import (
    AgentProgressMessage,
    ApprovalDecisionMessage,
    ApprovalRequiredMessage,
    NewEventMessage,
    NewEventPayload,
    SendMessageMessage,
)
from helpdesk.tickets.messages.events import TicketEvent as WireTicketEvent
from helpdesk.tickets.models import CommentEvent, Ticket, Visibility
from helpdesk.tickets.serializers.event import serialize_event

TicketFeedEvent = NewEventMessage | AgentProgressMessage | ApprovalRequiredMessage


class TicketTopic(Topic[TicketFeedEvent]):
    """One ticket's activity, addressed as `ticket:<id>`.

    Customer-visible: everything here is the record of what was said on the
    ticket, which is why sending a reply goes through the approval gate.
    """

    pattern = "ticket:{ticket_id}"

    async def authorize(self, **params: str) -> bool:
        return bool(await self._ticket_exists(params["ticket_id"]))

    @ws_handler(
        summary="Post a comment",
        description="Appends a CommentEvent and hands the ticket to triage.",
        output_type=NewEventMessage,
    )
    async def handle_send_message(self, message: SendMessageMessage) -> None:
        ticket_id = self.params["ticket_id"]
        event = await self._create_comment_event(
            ticket_id=ticket_id,
            content=message.payload.content,
            user=self.scope.get("user"),
            public=message.payload.public,
        )
        await self.broadcast(
            f"ticket:{ticket_id}",
            NewEventMessage(
                payload=NewEventPayload(event=await self._serialize(event))
            ),
        )

        if not settings.TRIAGE_ON_COMMENT:
            return

        # Only the requester saying something new asks for a reply. A staff note
        # is for colleagues, and a staff reply has already answered.
        if event.visibility != Visibility.PUBLIC or not await self._from_requester(
            ticket_id, self.scope.get("user")
        ):
            return

        from helpdesk.tickets.services.triage import start_triage

        user = self.scope.get("user")
        await start_triage(
            ticket_id, user.pk if user is not None and user.is_authenticated else None
        )

    @ws_handler(
        summary="Approve, edit, or reject the drafted reply",
        description="Resumes the paused run. Nothing reaches the customer until this arrives.",
        output_type=NewEventMessage | AgentProgressMessage,
    )
    async def handle_approval_decision(self, message: ApprovalDecisionMessage) -> None:
        from helpdesk.tickets.services.triage import start_approval

        user = self.scope.get("user")
        await start_approval(
            self.params["ticket_id"],
            approved=message.payload.approved,
            content=message.payload.content,
            user_id=user.pk if user is not None and user.is_authenticated else None,
        )

    # Relays: an event published to this topic goes straight to the client.
    @event_handler
    async def handle_new_event(self, event: NewEventMessage) -> NewEventMessage:
        return event

    @event_handler
    async def handle_progress(
        self, event: AgentProgressMessage
    ) -> AgentProgressMessage:
        return event

    @event_handler
    async def handle_approval_required(
        self, event: ApprovalRequiredMessage
    ) -> ApprovalRequiredMessage:
        return event

    @database_sync_to_async
    def _ticket_exists(self, ticket_id: str) -> bool:
        return Ticket.objects.filter(id=ticket_id).exists()

    @database_sync_to_async
    def _create_comment_event(
        self, ticket_id: str, content: str, user: Any, public: bool
    ) -> CommentEvent:
        author = user if user is not None and user.is_authenticated else None
        ticket = Ticket.objects.get(id=ticket_id)
        # The requester cannot write a note to themselves; everyone else chooses,
        # and the default is internal.
        theirs = author is not None and author.pk == ticket.created_by_id
        return CommentEvent.objects.create(
            ticket_id=ticket_id,
            content=content,
            created_by=author,
            visibility=(Visibility.PUBLIC if theirs or public else Visibility.INTERNAL),
        )

    @database_sync_to_async
    def _from_requester(self, ticket_id: str, user: Any) -> bool:
        if user is None or not user.is_authenticated:
            return False
        return Ticket.objects.filter(id=ticket_id, created_by_id=user.pk).exists()

    @database_sync_to_async
    def _serialize(self, event: Any) -> WireTicketEvent:
        return serialize_event(event)
