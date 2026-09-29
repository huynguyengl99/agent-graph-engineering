import uuid

from django.conf import settings
from django.db import models


class Conversation(models.Model):
    """A rep's thread with the assistant.

    Standalone by default, with an optional ticket it was opened about. That
    nullable link is what lets "ask about ticket #123" preload context without
    forcing every conversation to belong to a ticket.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, blank=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    ticket = models.ForeignKey(
        "tickets.Ticket",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversations",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["-updated_at"])]

    def __str__(self) -> str:
        return self.title or f"Conversation {self.id}"
