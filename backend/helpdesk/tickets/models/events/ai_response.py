"""AI response event model."""

from django.db import models

from .base import TicketEvent


class AIResponseEvent(TicketEvent):
    content = models.TextField()
    model_name = models.CharField(max_length=100, default="gpt-4")
    tokens_used = models.IntegerField(default=0)

    @classmethod
    def get_event_type(cls) -> str:
        return "ai_response"

    def __str__(self) -> str:
        return f"AI Response ({self.model_name}): {self.content[:50]}"
