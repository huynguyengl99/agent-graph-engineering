"""The state the agent hands back, and how it finds its way into the next run.

The agent keeps nothing between runs. What makes a decision land on the run it
was asked about, and a second question remember the first, is this service
storing the blob a run ended with and sending it out again. Lose it and a
parked run is unresumable with no error to say so: the agent is simply asked
to start something new.
"""

from typing import Any

from asgiref.sync import sync_to_async

from helpdesk.agent_client.agent_hub_support_topic.messages import (
    ApprovalRequiredMessage,
    ApprovalRequiredPayload,
    RunEndedMessage,
    RunEndedPayload,
)
from helpdesk.hub.consumer import HubConsumer
from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.models import AgentThread, PendingReply, Visibility
from helpdesk.tickets.services.support import (
    CUSTOMER,
    TEAM,
    _request,
    carried_state,
    relay,
)

PARKED = {"awaiting": "reply_approval", "answer": {"content": "Looking into it."}}


class TestWhatARunLeavesBehind(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user)

    async def end_run(self, visibility: str, awaiting: str, state: Any) -> None:
        await relay(str(self.ticket.id), visibility).on_event(
            RunEndedMessage(
                payload=RunEndedPayload(
                    thread_id=str(self.ticket.id), awaiting=awaiting, state=state
                )
            )
        )

    async def test_a_parked_run_is_stored_and_handed_back(self) -> None:
        await self.end_run(Visibility.PUBLIC, "reply_approval", PARKED)

        assert await carried_state(str(self.ticket.id), CUSTOMER) == PARKED

    async def test_a_finished_run_is_stored_too(self) -> None:
        """Not only parks: the thread's memory rides the same blob, and a run
        that answered is exactly the one the next question has to follow."""
        await self.end_run(Visibility.PUBLIC, "", {"messages_json": "[]"})

        thread = await AgentThread.objects.aget(ticket=self.ticket, audience=CUSTOMER)
        assert thread.awaiting == ""
        assert thread.state == {"messages_json": "[]"}

    async def test_the_two_lanes_do_not_overwrite_each_other(self) -> None:
        """A customer's run and the team's run about one ticket are two
        threads. One row for both and a team question would resume the
        customer's parked draft."""
        await self.end_run(Visibility.PUBLIC, "reply_approval", PARKED)
        await self.end_run(Visibility.INTERNAL, "", {"messages_json": "[]"})

        assert await carried_state(str(self.ticket.id), CUSTOMER) == PARKED
        assert await carried_state(str(self.ticket.id), TEAM) == {"messages_json": "[]"}

    async def test_the_next_request_carries_it(self) -> None:
        await self.end_run(Visibility.PUBLIC, "", {"messages_json": "[]"})

        request = await _request(
            str(self.ticket.id),
            "",
            None,
            await carried_state(str(self.ticket.id), CUSTOMER),
        )

        assert request.state == {"messages_json": "[]"}

    async def test_a_thread_nobody_has_worked_carries_nothing(self) -> None:
        assert await carried_state(str(self.ticket.id), CUSTOMER) == {}

    async def test_a_second_run_replaces_the_first(self) -> None:
        """One row per lane, so the blob is the latest rather than a history:
        an old park resent with a decision would resume the wrong gate."""
        await self.end_run(Visibility.PUBLIC, "reply_approval", PARKED)
        await self.end_run(Visibility.PUBLIC, "", {"messages_json": "[]"})

        rows = await sync_to_async(
            lambda: AgentThread.objects.filter(ticket=self.ticket).count()
        )()
        assert rows == 1
        assert await carried_state(str(self.ticket.id), CUSTOMER) == {
            "messages_json": "[]"
        }


class TestTheCardAndTheStateLandTogether(WebsocketTestCase):
    """They are two copies of the same draft. Written apart, a crash between
    them leaves a reviewer a card to answer and nothing to carry on from."""

    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user)

    def gate(self) -> ApprovalRequiredMessage:
        return ApprovalRequiredMessage(
            payload=ApprovalRequiredPayload(
                ticket_id=str(self.ticket.id), draft="Looking into it.", findings=[]
            )
        )

    async def test_a_run_that_reaches_the_end_writes_both(self) -> None:
        client = relay(str(self.ticket.id), Visibility.PUBLIC)

        await client.on_event(self.gate())
        await client.on_event(
            RunEndedMessage(
                payload=RunEndedPayload(
                    thread_id=str(self.ticket.id),
                    awaiting="reply_approval",
                    state=PARKED,
                )
            )
        )

        assert await PendingReply.objects.filter(ticket=self.ticket).aexists()
        assert await carried_state(str(self.ticket.id), CUSTOMER) == PARKED

    async def test_a_run_that_dies_at_the_gate_writes_neither(self) -> None:
        """The card used to be written as the gate went past, so this left one
        standing with no state behind it: answerable, and unresumable."""
        client = relay(str(self.ticket.id), Visibility.PUBLIC)

        await client.on_event(self.gate())

        assert not await PendingReply.objects.filter(ticket=self.ticket).aexists()
        assert await carried_state(str(self.ticket.id), CUSTOMER) == {}
