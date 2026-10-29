import uuid

from django.db import models


class AgentThread(models.Model):
    """The state the agent's last run on this thread ended with.

    The agent keeps nothing between runs: it hands its state back when a run
    ends and is sent it again with the next request. This is where that blob
    lives, so a park survives a reload, a redeploy and the agent process it
    was produced by.

    One row per lane, because a customer's run and the team's run about one
    ticket are two threads: they must not resume into each other, and the
    agent addresses them separately for the same reason.

    `awaiting` is what the run stopped for, empty when it simply finished. It
    is the one part of the blob this service reads: everything else is the
    agent's business and is handed back untouched.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        "tickets.Ticket", on_delete=models.CASCADE, related_name="agent_threads"
    )
    # "customer" or "team", as the agent's topic spells it.
    audience = models.CharField(max_length=10)

    awaiting = models.CharField(max_length=40, blank=True)
    state = models.JSONField(default=dict)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["ticket", "audience"], name="one_thread_per_ticket_audience"
            )
        ]

    def __str__(self) -> str:
        waiting = f" awaiting {self.awaiting}" if self.awaiting else ""
        return f"{self.audience} thread on {self.ticket_id}{waiting}"
