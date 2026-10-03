import uuid

from django.db import models


class PendingToolCall(models.Model):
    """A tool the agent proposed on a ticket, waiting on a person.

    The run is already durable in the agent's checkpointer; this is how the
    browser finds the card again after a reload or in a second tab.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.OneToOneField(
        "tickets.Ticket",
        on_delete=models.CASCADE,
        related_name="pending_tool_call",
    )

    tool = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    arguments = models.JSONField(default=dict)
    arguments_schema = models.JSONField(default=dict)
    unknown_arguments = models.JSONField(default=list)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.tool} awaiting approval on {self.ticket_id}"
