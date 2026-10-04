import uuid

from django.db import models

from helpdesk.tickets.models.events.base import Visibility


class TicketRun(models.Model):
    """A claim on one lane of one ticket, held while the agent is working it.

    The agent keys its checkpoint on the ticket and the audience, so two runs
    in the same lane are two graphs writing one thread. The second one wins,
    which is how an approved reply could vanish: a run parked at the gate, a
    message arriving a moment later started another, and the reviewer's approve
    resumed a thread whose interrupt had been overwritten.

    The claim outlives a park, because a parked run is still that lane's run -
    it is waiting for a person, not finished. `waiting` is whatever arrived
    behind it, which is started once the claim is released rather than dropped.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        "tickets.Ticket", on_delete=models.CASCADE, related_name="runs"
    )
    # The lane, as the rest of this app spells it.
    visibility = models.CharField(
        max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC
    )

    # Taken over once this is old enough: a worker killed mid-run would
    # otherwise hold the lane shut for good.
    claimed_at = models.DateTimeField(auto_now=True)

    waiting = models.BooleanField(default=False)
    # The team's lane asks a question; the customer's is the thread itself, so
    # a re-run picks their message up from the ticket without being told.
    waiting_question = models.TextField(blank=True)
    waiting_user_id = models.UUIDField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["ticket", "visibility"], name="one_run_per_ticket_lane"
            )
        ]

    def __str__(self) -> str:
        return f"{self.visibility} run on {self.ticket_id}"
