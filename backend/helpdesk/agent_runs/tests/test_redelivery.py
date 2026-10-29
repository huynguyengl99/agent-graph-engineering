"""What a redelivered task does, which is the half the settings only imply.

`test_run_tasks` asserts the two timeouts are ordered correctly. These assert
the behaviour that ordering exists to protect: a worker is killed mid-run, the
broker hands the task to another one, and the work has to happen exactly once
more - not never, because the dead run's claim is still sitting on the lane,
and not twice, because an early redelivery raced the run that is still going.

Driven through `run`, the real entry point, with only the relay to the agent
replaced: a broker cannot be made to lose a worker in a unit test, but what it
delivers afterwards is an ordinary call.
"""

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

from django.test import override_settings
from django.utils import timezone

from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.models import AgentThread, TicketRun, Visibility
from helpdesk.tickets.services.support import CUSTOMER, run


class TestARedeliveredRun(WebsocketTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user)

    def reaches_the_agent(self, relay: AsyncMock) -> AsyncMock:
        """A relay that completes.

        Left as a plain `MagicMock`, awaiting `handle()` raises `TypeError`,
        `run` catches it as an unreachable agent, and a test asserting only
        that the relay was built passes on a run that failed.
        """
        relay.return_value.handle = AsyncMock()
        return relay

    async def killed_mid_run(self, *, seconds_ago: int) -> TicketRun:
        """What a `kill -9` leaves behind: the claim, and nothing else.

        No state came back, because the run never reached the end that sends
        it, so the lane is held by a worker that no longer exists.
        """
        held = await TicketRun.objects.acreate(
            ticket=self.ticket, visibility=Visibility.PUBLIC
        )
        # `claimed_at` is auto_now, so it cannot be set on the way in.
        await TicketRun.objects.filter(pk=held.pk).aupdate(
            claimed_at=timezone.now() - timedelta(seconds=seconds_ago)
        )
        return held

    @override_settings(AGENT_RUN_CLAIM_TIMEOUT=300)
    @patch("helpdesk.tickets.services.support._Run")
    async def test_it_runs_once_the_lane_has_gone_stale(self, relay: AsyncMock) -> None:
        """The case the visibility timeout is sized for."""
        self.reaches_the_agent(relay)
        await self.killed_mid_run(seconds_ago=301)

        await run(str(self.ticket.id), visibility=Visibility.PUBLIC)

        relay.assert_called_once()
        relay.return_value.handle.assert_awaited_once()
        assert not await TicketRun.objects.filter(ticket=self.ticket).aexists(), (
            "the redelivered run should let the lane go when it finishes"
        )

    @override_settings(AGENT_RUN_CLAIM_TIMEOUT=300)
    @patch("helpdesk.tickets.services.support._Run")
    async def test_it_does_nothing_while_the_claim_is_fresh(
        self, relay: AsyncMock
    ) -> None:
        """Redelivered early, the task cannot tell a dead worker from a slow
        model, so it leaves the lane alone. That is the right call and it is
        also why `visibility_timeout` must outlast `AGENT_RUN_CLAIM_TIMEOUT`:
        every early delivery is a run that no-ops and then acks, and the work
        is gone."""
        await self.killed_mid_run(seconds_ago=5)

        await run(str(self.ticket.id), visibility=Visibility.PUBLIC)

        relay.assert_not_called()
        assert await TicketRun.objects.filter(ticket=self.ticket).aexists()

    @override_settings(AGENT_RUN_CLAIM_TIMEOUT=300)
    @patch("helpdesk.tickets.services.support._Run")
    async def test_the_crash_took_no_state_with_it(self, relay: AsyncMock) -> None:
        """The worker holds nothing, so there is nothing to recover.

        What the thread knows is in `AgentThread`, written when a run ends. A
        run killed before that leaves the previous one's state untouched, and
        the redelivered run is handed exactly what the dead one started from.
        """
        self.reaches_the_agent(relay)
        await AgentThread.objects.acreate(
            ticket=self.ticket,
            audience=CUSTOMER,
            awaiting="",
            state={"messages_json": "[]", "turn": "the one before"},
        )
        await self.killed_mid_run(seconds_ago=301)

        await run(str(self.ticket.id), visibility=Visibility.PUBLIC)

        request = relay.call_args.args[2]
        assert request.state == {"messages_json": "[]", "turn": "the one before"}, (
            "the redelivered run started from somewhere other than where the "
            "killed one did"
        )

    @override_settings(AGENT_RUN_CLAIM_TIMEOUT=300)
    @patch("helpdesk.tickets.services.support._Run")
    async def test_a_question_queued_behind_the_dead_run_is_not_lost(
        self, relay: AsyncMock
    ) -> None:
        """Somebody wrote in while the worker was dying. Taking the lane over
        must not drop what was waiting on the run that held it."""
        self.reaches_the_agent(relay)
        held = await self.killed_mid_run(seconds_ago=301)
        await TicketRun.objects.filter(pk=held.pk).aupdate(
            waiting=True, waiting_question="and what about the second charge?"
        )

        await run(str(self.ticket.id), visibility=Visibility.PUBLIC)

        asked: list[Any] = [call.args[2].question for call in relay.call_args_list]
        assert "and what about the second charge?" in asked, asked

    @override_settings(AGENT_RUN_CLAIM_TIMEOUT=300)
    @patch("helpdesk.tickets.services.support._Run")
    async def test_a_customer_thread_is_not_worked_twice(
        self, relay: AsyncMock
    ) -> None:
        """The other half of that rule. A customer queues no question - their
        message is on the ticket and the re-run reads the thread - so a lane
        marked as waiting with nothing in it would answer them a second time
        for no reason."""
        self.reaches_the_agent(relay)
        held = await self.killed_mid_run(seconds_ago=301)
        await TicketRun.objects.filter(pk=held.pk).aupdate(
            waiting=True, waiting_question=""
        )

        await run(str(self.ticket.id), visibility=Visibility.PUBLIC)

        relay.assert_called_once()
