"""Assignment event model."""

from django.conf import settings
from django.db import models

from .base import TicketEvent


class AssignmentEvent(TicketEvent):
    old_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="old_assignments",
    )
    new_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="new_assignments",
    )

    @classmethod
    def get_event_type(cls) -> str:
        return "assignment"

    def __str__(self) -> str:
        old = self.old_assignee.email if self.old_assignee else "Unassigned"
        new = self.new_assignee.email if self.new_assignee else "Unassigned"
        return f"Assigned: {old} → {new}"
