"""One run at a time per lane.

The agent keys its checkpoint on the ticket and the audience, so a second run
in the same lane overwrites the first one's interrupt. That is how an approved
reply vanished: a run parked at the gate, the customer sent another message a
moment later, and approve resumed a thread with nothing parked in it.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

from django.test import override_settings

import pytest

from helpdesk.accounts.factories import UserFactory
from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.models import PendingReply, TicketRun, Visibility
from helpdesk.tickets.services import lanes
from helpdesk.tickets.services.support import run


@pytest.fixture
def ticket(db: Any) -> Any:
    return TicketFactory.create(created_by=UserFactory.create())


class TestClaimingTheLane:
    def test_the_first_run_gets_it(self, ticket: Any) -> None:
        assert lanes.claim_sync(str(ticket.id), Visibility.PUBLIC, "", None)

    def test_the_second_waits_instead(self, ticket: Any) -> None:
        lanes.claim_sync(str(ticket.id), Visibility.PUBLIC, "", None)

        assert not lanes.claim_sync(str(ticket.id), Visibility.PUBLIC, "and this", None)
        held = TicketRun.objects.get(ticket=ticket, visibility=Visibility.PUBLIC)
        assert held.waiting
        assert held.waiting_question == "and this"

    def test_the_other_lane_is_not_blocked(self, ticket: Any) -> None:
        """A customer's run and the team's run about one ticket are two threads
        in the agent, so they are two claims here."""
        lanes.claim_sync(str(ticket.id), Visibility.PUBLIC, "", None)

        assert lanes.claim_sync(str(ticket.id), Visibility.INTERNAL, "", None)

    @override_settings(AGENT_RUN_CLAIM_TIMEOUT=-1)
    def test_a_claim_nobody_is_holding_is_taken_over(self, ticket: Any) -> None:
        """A worker killed mid-run would otherwise shut the lane for good, and
        the person waiting cannot tell that from a slow model."""
        lanes.claim_sync(str(ticket.id), Visibility.PUBLIC, "", None)

        assert lanes.claim_sync(str(ticket.id), Visibility.PUBLIC, "", None)


class TestLettingItGo:
    def test_nothing_waiting_frees_the_lane(self, ticket: Any) -> None:
        lanes.claim_sync(str(ticket.id), Visibility.PUBLIC, "", None)

        assert lanes.release_sync(str(ticket.id), Visibility.PUBLIC) is None
        assert not TicketRun.objects.filter(ticket=ticket).exists()

    def test_what_waited_comes_back(self, ticket: Any) -> None:
        lanes.claim_sync(str(ticket.id), Visibility.PUBLIC, "", None)
        lanes.claim_sync(str(ticket.id), Visibility.PUBLIC, "answer this next", None)

        queued = lanes.release_sync(str(ticket.id), Visibility.PUBLIC)

        assert queued is not None
        assert queued.question == "answer this next"

    def test_the_lane_stays_claimed_while_that_one_is_answered(
        self, ticket: Any
    ) -> None:
        """Handing the claim back first left the lane open for the length of
        the follow-up, which is the race the claim exists to stop."""
        lanes.claim_sync(str(ticket.id), Visibility.PUBLIC, "", None)
        lanes.claim_sync(str(ticket.id), Visibility.PUBLIC, "and this", None)

        lanes.release_sync(str(ticket.id), Visibility.PUBLIC)

        held = TicketRun.objects.get(ticket=ticket, visibility=Visibility.PUBLIC)
        assert not held.waiting
        assert not lanes.claim_sync(str(ticket.id), Visibility.PUBLIC, "later", None)

    def test_a_parked_run_keeps_it(self, ticket: Any) -> None:
        """Waiting for a person is not being finished, and the resume needs the
        interrupt it parked on to still be there."""
        lanes.claim_sync(str(ticket.id), Visibility.PUBLIC, "", None)
        PendingReply.objects.create(
            ticket=ticket, draft="Sorted.", visibility=Visibility.PUBLIC
        )

        assert lanes.release_sync(str(ticket.id), Visibility.PUBLIC) is None
        assert TicketRun.objects.filter(ticket=ticket).exists()

    def test_it_does_not_keep_the_other_lane_shut(self, ticket: Any) -> None:
        """A draft waiting on a reviewer used to hold the team's lane too, so a
        question asked while it sat there was queued and never run."""
        lanes.claim_sync(str(ticket.id), Visibility.INTERNAL, "", None)
        PendingReply.objects.create(
            ticket=ticket, draft="Sorted.", visibility=Visibility.PUBLIC
        )

        lanes.release_sync(str(ticket.id), Visibility.INTERNAL)

        assert not TicketRun.objects.filter(
            ticket=ticket, visibility=Visibility.INTERNAL
        ).exists()


class TestTheRunItself(WebsocketTestCase):
    """Driving the real entry point, with only the relay to the agent replaced."""

    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user)

    @patch("helpdesk.tickets.services.support._Run")
    async def test_a_second_run_does_not_start(self, relay: AsyncMock) -> None:
        await lanes.claim(str(self.ticket.id), Visibility.PUBLIC, "", None)

        await run(str(self.ticket.id), visibility=Visibility.PUBLIC)

        relay.assert_not_called()

    @patch("helpdesk.tickets.services.support._Run")
    async def test_what_queued_behind_it_is_answered(self, relay: AsyncMock) -> None:
        """Dropping it would lose a customer's message to nothing more than
        their timing."""

        async def queue_one_then_stop(*_args: Any, **_kwargs: Any) -> None:
            if relay.call_count == 1:
                await lanes.claim(
                    str(self.ticket.id), Visibility.PUBLIC, "and this", None
                )

        relay.return_value.handle = AsyncMock(side_effect=queue_one_then_stop)

        await run(str(self.ticket.id), visibility=Visibility.PUBLIC)

        assert relay.call_count == 2
        assert not await TicketRun.objects.filter(ticket=self.ticket).aexists()
