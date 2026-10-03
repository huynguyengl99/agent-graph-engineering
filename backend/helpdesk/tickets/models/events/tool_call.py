"""Tool call event model."""

from django.db import models

from .base import TicketEvent


class ToolCallEvent(TicketEvent):
    """What a tool did on this ticket, once it has done it."""

    tool = models.CharField(max_length=100)
    arguments = models.JSONField(default=dict)
    result = models.TextField(blank=True)
    error = models.TextField(blank=True)
    cancelled = models.BooleanField(default=False)

    @classmethod
    def get_event_type(cls) -> str:
        return "tool_call"

    def __str__(self) -> str:
        return f"{self.tool} on {self.ticket_id}"
