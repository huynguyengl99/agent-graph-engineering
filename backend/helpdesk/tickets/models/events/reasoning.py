"""Reasoning event model."""

from django.db import models

from .base import TicketEvent


class ReasoningEvent(TicketEvent):
    """Why the agent took the branch it took.

    Always internal, including on a run the customer's own message started:
    they asked a question, not for the workings.
    """

    # Which step explained itself: a run has several that do.
    step = models.CharField(max_length=40, blank=True)
    content = models.TextField()
    decision = models.CharField(max_length=60, blank=True)
    model_name = models.CharField(max_length=100, blank=True)

    @classmethod
    def get_event_type(cls) -> str:
        return "reasoning"

    def __str__(self) -> str:
        return f"Reasoning for {self.decision} on {self.ticket_id}"
