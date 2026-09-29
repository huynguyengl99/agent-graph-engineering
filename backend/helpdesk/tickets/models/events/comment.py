"""Comment event model."""
from django.db import models

from .base import TicketEvent


class CommentEvent(TicketEvent):
    content = models.TextField()

    @classmethod
    def get_event_type(cls) -> str:
        return "comment"

    def __str__(self) -> str:
        return f"Comment by {self.created_by}: {self.content[:50]}"
