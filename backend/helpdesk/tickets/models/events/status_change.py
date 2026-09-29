"""Status change event model."""
from django.db import models

from helpdesk.tickets.models.ticket import TicketStatus

from .base import TicketEvent


class StatusChangeEvent(TicketEvent):
    old_status = models.CharField(max_length=20, choices=TicketStatus.choices)
    new_status = models.CharField(max_length=20, choices=TicketStatus.choices)

    @classmethod
    def get_event_type(cls) -> str:
        return "status_change"

    def __str__(self) -> str:
        return f"Status: {self.old_status} → {self.new_status}"
