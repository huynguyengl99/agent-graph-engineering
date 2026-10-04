"""One run at a time per lane of a ticket.

The agent keys its checkpoint on the ticket and the audience. Two runs in that
lane are two graphs writing one thread, and the second one wins - which is how
an approved reply could vanish: a run parked at the gate, a message arriving a
moment later started another, and approve resumed a thread whose interrupt had
been overwritten.

So a run claims its lane, and whatever arrives behind it waits rather than
racing it. The claim is held through a park, because a run waiting for a person
is still that lane's run.
"""

from datetime import timedelta
from typing import Any, NamedTuple

from channels.db import database_sync_to_async
from django.conf import settings
from django.db import transaction
from django.utils import timezone

import structlog

from helpdesk.tickets.models import PendingReply, PendingToolCall, TicketRun

logger = structlog.get_logger(__name__)


class Queued(NamedTuple):
    """What was asked for while the lane was busy."""

    question: str
    user_id: Any


def claim_sync(ticket_id: str, visibility: str, question: str, user_id: Any) -> bool:
    """Take the lane, or leave the request behind the run that holds it.

    A claim older than `AGENT_RUN_CLAIM_TIMEOUT` is taken over: a worker killed
    mid-run would otherwise hold the lane shut for good, and the person waiting
    has no way to tell that from a slow model.
    """
    stale = timezone.now() - timedelta(seconds=settings.AGENT_RUN_CLAIM_TIMEOUT)
    with transaction.atomic():
        run, created = TicketRun.objects.select_for_update().get_or_create(
            ticket_id=ticket_id,
            visibility=visibility,
            defaults={"waiting_question": "", "waiting_user_id": user_id},
        )
        if created:
            return True
        if run.claimed_at < stale:
            logger.warning(
                "support.claim_taken_over", ticket_id=ticket_id, lane=visibility
            )
            run.waiting = False
            run.waiting_question = ""
            run.save(update_fields=["waiting", "waiting_question", "claimed_at"])
            return True

        # Last one wins on purpose: two messages while the agent works mean the
        # later one is what they want answered, and both are on the ticket
        # either way.
        run.waiting = True
        run.waiting_question = question
        run.waiting_user_id = user_id
        run.save(update_fields=["waiting", "waiting_question", "waiting_user_id"])
        return False


def release_sync(ticket_id: str, visibility: str) -> Queued | None:
    """Give the lane up, unless this lane's run is parked on a person.

    Both gates record which lane parked them, and that matters here: a draft
    waiting for approval in the customer's lane used to hold the team's lane
    shut as well, so a question asked while it sat there was queued and never
    run.

    Returns what was waiting, which the caller then runs: doing it here would
    make this a sync function that starts an async run.
    """
    parked = (
        PendingReply.objects.filter(ticket_id=ticket_id, visibility=visibility).exists()
        or PendingToolCall.objects.filter(
            ticket_id=ticket_id, visibility=visibility
        ).exists()
    )
    if parked:
        return None

    with transaction.atomic():
        run = (
            TicketRun.objects.select_for_update()
            .filter(ticket_id=ticket_id, visibility=visibility)
            .first()
        )
        if run is None:
            return None
        queued = (
            Queued(run.waiting_question, run.waiting_user_id) if run.waiting else None
        )
        run.delete()
    return queued


claim = database_sync_to_async(claim_sync)
release = database_sync_to_async(release_sync)
