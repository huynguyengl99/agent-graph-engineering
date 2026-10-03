"""Handoff event model."""

from django.db import models

from helpdesk.tickets.models.ticket import Handling

from .base import TicketEvent


class HandoffEvent(TicketEvent):
    """A change of who is answering, and why."""

    handling = models.CharField(max_length=20, choices=Handling.choices)
    reason = models.TextField(blank=True)

    @classmethod
    def get_event_type(cls) -> str:
        return "handoff"

    def __str__(self) -> str:
        return f"Handoff to {self.handling}"
