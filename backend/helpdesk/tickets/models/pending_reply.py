import uuid

from django.db import models


class PendingReply(models.Model):
    """A drafted reply parked at the agent's approval gate.

    The run is already durable in the agent's checkpointer. This row is how the
    browser finds it again: the draft used to live only on the relay client
    instance, which is discarded when the socket closes, and in the React state
    of whichever tab was open. A reload lost a customer-facing draft while the
    graph stayed parked.

    It is also the answer to what gets recorded on the ticket. The agent's
    `reply_sent` carries a receipt, not the text, so without this a plain
    approve persisted an empty event.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.OneToOneField(
        "tickets.Ticket",
        on_delete=models.CASCADE,
        related_name="pending_reply",
    )

    draft = models.TextField()
    findings = models.JSONField(default=list)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"reply awaiting approval on {self.ticket_id}"
