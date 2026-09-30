import uuid

from django.db import models


class PendingApproval(models.Model):
    """A tool call parked at the agent's gate, waiting on a person.

    The agent's checkpointer already holds the run durably. This row exists so
    the *browser* can find it again: the proposal used to arrive as a single
    WebSocket frame into React state, so a reload or a second tab lost the card
    while the graph stayed parked forever with no way back to it.

    Deleted when decided rather than kept as history. What a reviewer approved
    becomes the tool result and the answer; what they cancelled leaves the
    assistant saying so. Neither needs a second record here.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.OneToOneField(
        "conversations.Conversation",
        on_delete=models.CASCADE,
        related_name="pending_approval",
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
        return f"{self.tool} awaiting approval on {self.conversation_id}"
