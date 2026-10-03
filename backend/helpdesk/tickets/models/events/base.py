"""Base ticket event model using django-polymorphic."""

from django.conf import settings
from django.db import models

from polymorphic.models import PolymorphicModel

from helpdesk.tickets.models.ticket import Ticket


class Visibility(models.TextChoices):
    """Who an event is for.

    Internal by default, so reaching the customer is the deliberate act. A
    requester's own message is public because they wrote it.
    """

    INTERNAL = "internal", "Internal"
    PUBLIC = "public", "Public"


class TicketEvent(PolymorphicModel):
    """
    Polymorphic base model for ticket events.

    This demonstrates the polymorphic pattern where different event types
    (comments, status changes, assignments, AI responses) share a common base
    but have different fields.

    The polymorphic_ctype field (added automatically by django-polymorphic)
    acts as the discriminator for querying and serialization.
    """

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="events",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_events",
    )
    visibility = models.CharField(
        max_length=10, choices=Visibility.choices, default=Visibility.INTERNAL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["ticket", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_event_type()} on {self.ticket.title}"

    @classmethod
    def get_event_type(cls) -> str:
        """The discriminator the frontend switches on.

        A classmethod because the polymorphic serializer needs it both for a
        concrete instance and for the model class during schema generation.
        """
        return "event"
