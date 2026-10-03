"""Who is answering a ticket, and the record of that changing."""

from typing import Any

from channels.db import database_sync_to_async
from django.db import transaction

from helpdesk.tickets.messages.events import TicketEvent as WireTicketEvent
from helpdesk.tickets.models import Handling, HandoffEvent, Ticket
from helpdesk.tickets.serializers.event import serialize_event


@database_sync_to_async
def hand_off(
    ticket_id: str,
    handling: str,
    *,
    reason: str = "",
    user: Any = None,
) -> WireTicketEvent | None:
    """Move the ticket, or return None when it is already there."""
    author = (
        user if user is not None and getattr(user, "is_authenticated", False) else None
    )
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(id=ticket_id)
        if ticket.handling == handling:
            return None

        ticket.handling = handling
        changed = ["handling"]
        if handling == Handling.WITH_STAFF and author is not None:
            ticket.assigned_to = author
            changed.append("assigned_to")
        ticket.save(update_fields=changed)

        return serialize_event(
            HandoffEvent.objects.create(
                ticket_id=ticket_id,
                handling=handling,
                reason=reason,
                created_by=author,
            )
        )


@database_sync_to_async
def handling_of(ticket_id: str) -> str:
    return str(Ticket.objects.values_list("handling", flat=True).get(id=ticket_id))
