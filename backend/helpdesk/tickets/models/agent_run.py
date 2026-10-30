import uuid

from django.db import models


class AgentRun(models.Model):
    """One run on a thread, and the state it ended with.

    `AgentThread` keeps only the latest, because that is all a resume needs.
    This keeps every one, in order, which is what answers the questions a
    reviewer asks afterwards: what did the agent know when it proposed that
    refund, and what changed between the run that stopped and the one that
    carried on.

    `run_id` comes out of the state the agent handed back and is the same id
    its tracer files spans under, so a row here and a trace are two halves of
    one turn with no extra plumbing between them. A run that stopped and the
    one that carried it on share that id, because the decision carries the
    same context back: two rows, one trace, which is the turn.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        "tickets.Ticket", on_delete=models.CASCADE, related_name="agent_runs"
    )
    audience = models.CharField(max_length=10)

    run_id = models.CharField(max_length=64, blank=True)
    awaiting = models.CharField(max_length=40, blank=True)
    state = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["ticket", "audience", "created_at"]),
            models.Index(fields=["run_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.audience} run {self.run_id[:8]} on {self.ticket_id}"
