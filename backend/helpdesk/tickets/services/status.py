"""The ticket's own fields: what it is about, and whether it is done."""

from typing import Any

from channels.db import database_sync_to_async
from django.db import transaction

from helpdesk.tickets.messages import TicketUpdatedMessage, TicketUpdatedPayload
from helpdesk.tickets.messages.events import TicketEvent as WireTicketEvent
from helpdesk.tickets.models import StatusChangeEvent, Ticket, Visibility
from helpdesk.tickets.serializers.event import serialize_event


@database_sync_to_async
def set_priority(ticket_id: str, priority: str) -> bool:
    """The agent's reading of the ticket, applied. Returns whether it moved."""
    ticket = Ticket.objects.get(id=ticket_id)
    if ticket.priority == priority:
        return False
    ticket.priority = priority
    ticket.save(update_fields=["priority"])
    return True


@database_sync_to_async
def set_status(ticket_id: str, status: str, user: Any = None) -> WireTicketEvent | None:
    """Closing a ticket is part of its record, so it leaves one."""
    author = (
        user if user is not None and getattr(user, "is_authenticated", False) else None
    )
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(id=ticket_id)
        if ticket.status == status:
            return None

        was, ticket.status = ticket.status, status
        ticket.save(update_fields=["status"])
        return serialize_event(
            StatusChangeEvent.objects.create(
                ticket_id=ticket_id,
                old_status=was,
                new_status=status,
                created_by=author,
                visibility=Visibility.PUBLIC,
            )
        )


@database_sync_to_async
def ticket_state(ticket_id: str) -> TicketUpdatedMessage:
    ticket = Ticket.objects.get(id=ticket_id)
    return TicketUpdatedMessage(
        payload=TicketUpdatedPayload(status=ticket.status, priority=ticket.priority)
    )
