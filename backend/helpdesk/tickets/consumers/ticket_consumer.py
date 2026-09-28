import asyncio
from typing import Any

from channels.db import database_sync_to_async
from django.conf import settings

from chanx.channels.websocket import AsyncJsonWebsocketConsumer
from chanx.core.decorators import channel, ws_handler
from chanx.messages.incoming import PingMessage
from chanx.messages.outgoing import PongMessage

from helpdesk.core.ws_camel import CamelCaseJSONMixin
from helpdesk.tickets.messages import (
    AgentProgressMessage,
    ApprovalDecisionMessage,
    ApprovalRequiredMessage,
    CompleteStreamingMessage,
    NewEventMessage,
    NewEventPayload,
    SendMessageMessage,
    StreamingMessage,
)
from helpdesk.tickets.messages.events import TicketEvent as WireTicketEvent
from helpdesk.tickets.models import CommentEvent, Ticket
from helpdesk.tickets.serializers.event import serialize_event
from helpdesk.tickets.services.triage import run_triage, submit_approval


@channel(
    name="tickets",
    description="Realtime ticket activity: comments and streamed agent answers",
    tags=["tickets", "realtime"],
)
class TicketConsumer(CamelCaseJSONMixin, AsyncJsonWebsocketConsumer):
    """One socket per ticket. Every connected client sees the same event log."""

    async def post_authentication(self) -> None:
        assert self.channel_layer
        # The `<uuid:...>` converter hands back a UUID instance, not a string.
        self.ticket_id: str = str(self.scope["url_route"]["kwargs"]["ticket_id"])

        if not await self._ticket_exists(self.ticket_id):
            await self.close()
            return

        self.group_name = f"ticket_{self.ticket_id}"
        self.groups.append(self.group_name)
        await self.channel_layer.group_add(self.group_name, self.channel_name)

    @ws_handler
    async def handle_ping(self, _message: PingMessage) -> PongMessage:
        return PongMessage()

    @ws_handler(
        summary="Post a comment",
        description=(
            "Appends a CommentEvent to the ticket, fans it out to every "
            "connected client, then hands the ticket to the triage agent."
        ),
        output_type=(
            NewEventMessage
            | StreamingMessage
            | CompleteStreamingMessage
            | AgentProgressMessage
            | ApprovalRequiredMessage
        ),
    )
    async def handle_send_message(self, message: SendMessageMessage) -> None:
        event = await self._create_comment_event(
            ticket_id=self.ticket_id,
            content=message.payload.content,
            user=self.scope.get("user"),
        )
        await self.broadcast_message(
            NewEventMessage(payload=NewEventPayload(event=await self._serialize(event)))
        )

        if not settings.TRIAGE_ON_COMMENT:
            return

        # Triage runs detached: the agent may take tens of seconds, and this
        # handler must not hold the socket open waiting for it. Results reach
        # the client through the ticket group, not through this return path.
        ticket = await self._ticket_context(self.ticket_id)
        self._triage_task = asyncio.create_task(
            run_triage(
                ticket_id=self.ticket_id,
                title=ticket["title"],
                description=ticket["description"],
                history=ticket["history"],
            )
        )

    @ws_handler(
        summary="Approve, edit, or reject the agent's drafted reply",
        description=(
            "Resumes the paused triage run. Nothing reaches the customer until "
            "this arrives."
        ),
        output_type=NewEventMessage | AgentProgressMessage,
    )
    async def handle_approval_decision(
        self, message: ApprovalDecisionMessage
    ) -> None:
        # Detached for the same reason as triage: the resume runs a graph.
        self._approval_task = asyncio.create_task(
            submit_approval(
                ticket_id=self.ticket_id,
                approved=message.payload.approved,
                content=message.payload.content,
            )
        )

    @database_sync_to_async
    def _ticket_exists(self, ticket_id: str) -> bool:
        return Ticket.objects.filter(id=ticket_id).exists()

    @database_sync_to_async
    def _create_comment_event(
        self, ticket_id: str, content: str, user: Any
    ) -> CommentEvent:
        return CommentEvent.objects.create(
            ticket_id=ticket_id,
            content=content,
            created_by=user if user is not None and user.is_authenticated else None,
        )

    @database_sync_to_async
    def _serialize(self, event: Any) -> WireTicketEvent:
        return serialize_event(event)

    @database_sync_to_async
    def _ticket_context(self, ticket_id: str) -> dict[str, Any]:
        ticket = Ticket.objects.get(id=ticket_id)
        comments = (
            CommentEvent.objects.filter(ticket_id=ticket_id)
            .order_by("created_at")
            .values_list("content", flat=True)
        )
        return {
            "title": ticket.title,
            "description": ticket.description,
            "history": list(comments),
        }
