"""Telling the customer that somebody has their ticket.

Everything else the agent broadcasts while it works - the stage it is on, what
it decided, the reasoning as it is written - is the team's. So the customer
watched an empty thread between sending a message and the reply landing, with
nothing to say it had been received.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

from helpdesk.hub.consumer import HubConsumer
from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.models import Visibility
from helpdesk.tickets.services.support import run
from helpdesk.tickets.topics.ticket_topic import TicketFeedEvent


class TestTheCustomerIsToldSomebodyIsOnIt(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        self.ticket = TicketFactory.create(created_by=self.user)
        self.topic = f"ticket:{self.ticket.id}"

    async def sent(self, visibility: str) -> list[Any]:
        """Each broadcast terminates with its own completion frame, so the
        start and the stop are two reads rather than one."""
        await self.subscribe_ready(self.topic)
        with patch("helpdesk.tickets.services.support._Run") as relay:
            relay.return_value.handle = AsyncMock()
            await run(str(self.ticket.id), visibility=visibility)

        messages: list[Any] = []
        for _ in range(2):
            messages += await self.receive_topic_messages(TicketFeedEvent)
        return messages

    async def test_it_starts_and_stops_around_the_run(self) -> None:
        sent = await self.sent(Visibility.PUBLIC)

        assert [m.action for m in sent] == ["agent_working", "agent_working"]
        assert [m.payload.working for m in sent] == [True, False]

    async def test_a_run_in_the_teams_lane_says_nothing(self) -> None:
        """Their own question, their own progress rows. The customer has no
        reason to see a spinner for work that is not about answering them."""
        assert await self.sent(Visibility.INTERNAL) == []


class TestWhatItCarries(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user)

    async def test_only_the_fact_that_it_is_working(self) -> None:
        """Which step, what it decided and what it read stay with the team."""
        await self.subscribe_ready(f"ticket:{self.ticket.id}")
        with patch("helpdesk.tickets.services.support._Run") as relay:
            relay.return_value.handle = AsyncMock()
            await run(str(self.ticket.id), visibility=Visibility.PUBLIC)

        [started] = await self.receive_topic_messages(TicketFeedEvent)

        assert set(started.payload.model_dump()) == {"working"}


class TestStaffSeeItToo(WebsocketTestCase):
    """They are watching the same thread the customer is."""

    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.ticket = TicketFactory.create(created_by=self.user)

    async def test_the_signal_is_not_stripped_for_staff(self) -> None:
        await self.subscribe_ready(f"ticket:{self.ticket.id}")
        with patch("helpdesk.tickets.services.support._Run") as relay:
            relay.return_value.handle = AsyncMock()
            await run(str(self.ticket.id), visibility=Visibility.PUBLIC)

        messages: list[Any] = await self.receive_topic_messages(
            TicketFeedEvent, stop_action="event_complete"
        )

        assert any(m.action == "agent_working" for m in messages)
