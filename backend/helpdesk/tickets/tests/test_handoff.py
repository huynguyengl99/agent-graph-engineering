"""Who answers a ticket, as it changes hands."""

import asyncio
from unittest.mock import AsyncMock, patch

from django.test import override_settings

from helpdesk.accounts.factories import UserFactory
from helpdesk.agent_client.agent_hub_triage_topic.messages import (
    ApprovalRequiredMessage,
    ApprovalRequiredPayload,
    ReplySentMessage,
    ReplySentPayload,
    TriageRequestPayload,
)
from helpdesk.core.consumers.hub import HubConsumer
from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.messages import (
    ReturnToAgentMessage,
    ReturnToAgentPayload,
    SendMessageMessage,
    SendMessagePayload,
)
from helpdesk.tickets.models import AIResponseEvent, Handling, Ticket, Visibility
from helpdesk.tickets.services.handoff import hand_off, handling_of
from helpdesk.tickets.services.triage import TicketTriageClient, _parked_visibility
from helpdesk.tickets.topics.ticket_topic import TicketFeedEvent


async def settled(mock: AsyncMock, *, expected: int = 1) -> int:
    """The handler broadcasts before it calls the agent, so the test's own
    receive loop returns first."""
    for _ in range(50):
        if mock.await_count >= expected:
            break
        await asyncio.sleep(0.01)
    return int(mock.await_count)


class TestHandOff(WebsocketTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user)

    async def test_a_new_ticket_is_the_agents(self) -> None:
        assert await handling_of(str(self.ticket.id)) == Handling.AGENT

    async def test_moving_it_records_why(self) -> None:
        event = await hand_off(
            str(self.ticket.id), Handling.NEEDS_HUMAN, reason="Needs billing access"
        )

        assert event is not None
        assert event.handling == Handling.NEEDS_HUMAN
        assert event.reason == "Needs billing access"
        assert await handling_of(str(self.ticket.id)) == Handling.NEEDS_HUMAN

    async def test_moving_it_where_it_already_is_changes_nothing(self) -> None:
        """Two escalations in a run would otherwise be two rows in the timeline."""
        await hand_off(str(self.ticket.id), Handling.NEEDS_HUMAN)

        assert await hand_off(str(self.ticket.id), Handling.NEEDS_HUMAN) is None

    async def test_staff_taking_it_are_assigned_it(self) -> None:
        staff = await UserFactory.acreate(is_staff=True)

        await hand_off(str(self.ticket.id), Handling.WITH_STAFF, user=staff)

        fresh = await Ticket.objects.aget(id=self.ticket.id)
        assert fresh.assigned_to_id == staff.pk

    async def test_a_handoff_is_internal(self) -> None:
        """The customer sees the staff reply, not the plumbing behind it."""
        event = await hand_off(str(self.ticket.id), Handling.NEEDS_HUMAN)

        assert event is not None
        assert event.visibility == "internal"


class TestTakingTheTicket(WebsocketTestCase):
    """The agent answers until a person does."""

    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.customer = UserFactory.create()
        self.ticket = TicketFactory.create(created_by=self.customer)
        self.topic = f"ticket:{self.ticket.id}"

    async def reply(self, *, public: bool) -> None:
        await self.subscribe_ready(self.topic)
        await self.auth_communicator.send_message(
            SendMessageMessage(
                payload=SendMessagePayload(content="Looking into it.", public=public)
            ),
            topic=self.topic,
        )
        await self.receive_topic_messages(TicketFeedEvent, stop_action="event_complete")

    async def test_answering_the_customer_takes_the_ticket(self) -> None:
        await self.reply(public=True)

        assert await handling_of(str(self.ticket.id)) == Handling.WITH_STAFF

    async def test_a_note_to_the_team_does_not(self) -> None:
        """A note is not an answer, and the agent is still the one replying."""
        await self.reply(public=False)

        assert await handling_of(str(self.ticket.id)) == Handling.AGENT

    @override_settings(TRIAGE_ON_COMMENT=True)
    @patch("helpdesk.tickets.services.triage.start_triage")
    async def test_the_agent_stays_quiet_once_staff_have_it(
        self, start: AsyncMock
    ) -> None:
        await hand_off(str(self.ticket.id), Handling.WITH_STAFF, user=self.user)
        await self.subscribe_ready(self.topic)

        await self.auth_communicator.send_message(
            SendMessageMessage(
                payload=SendMessagePayload(content="Any news?", public=True)
            ),
            topic=self.topic,
        )
        await self.receive_topic_messages(TicketFeedEvent, stop_action="event_complete")

        assert await settled(start) == 0

    async def test_handing_it_back_puts_the_agent_in_charge(self) -> None:
        await hand_off(str(self.ticket.id), Handling.WITH_STAFF, user=self.user)
        await self.subscribe_ready(self.topic)

        await self.auth_communicator.send_message(
            ReturnToAgentMessage(payload=ReturnToAgentPayload(reason="Resolved")),
            topic=self.topic,
        )
        await self.receive_topic_messages(TicketFeedEvent, stop_action="event_complete")

        assert await handling_of(str(self.ticket.id)) == Handling.AGENT


class TestTheAgentStillAnswers(WebsocketTestCase):
    """The gate above has to let the ordinary case through."""

    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user)
        self.topic = f"ticket:{self.ticket.id}"

    @override_settings(TRIAGE_ON_COMMENT=True)
    @patch("helpdesk.tickets.services.triage.start_triage")
    async def test_the_requester_asking_again_reaches_the_agent(
        self, start: AsyncMock
    ) -> None:
        assert await handling_of(str(self.ticket.id)) == Handling.AGENT
        await self.subscribe_ready(self.topic)
        await self.auth_communicator.send_message(
            SendMessageMessage(
                payload=SendMessagePayload(content="Any news?", public=True)
            ),
            topic=self.topic,
        )
        await self.receive_topic_messages(TicketFeedEvent, stop_action="event_complete")

        assert await settled(start) == 1


class TestWhoTheReplyIsFor(WebsocketTestCase):
    """A draft asked for as a note must not be sent to the customer by the
    approve button."""

    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user)

    def client_for(self, visibility: str) -> TicketTriageClient:
        return TicketTriageClient(
            str(self.ticket.id),
            TriageRequestPayload(
                ticket_id=str(self.ticket.id), title="x", description="y"
            ),
            visibility=visibility,
        )

    async def test_an_internal_draft_stays_internal_through_the_gate(self) -> None:
        await self.subscribe_ready(f"ticket:{self.ticket.id}")
        await self.client_for(Visibility.INTERNAL).on_event(
            ApprovalRequiredMessage(
                payload=ApprovalRequiredPayload(
                    ticket_id=str(self.ticket.id), draft="Draft.", findings=[]
                )
            )
        )

        assert await _parked_visibility(str(self.ticket.id)) == Visibility.INTERNAL

    async def test_an_answer_the_agent_sends_reaches_the_customer(self) -> None:
        client = self.client_for(Visibility.PUBLIC)
        client.pending_reply = "Sorted."
        await self.subscribe_ready(f"ticket:{self.ticket.id}")

        await client.on_event(
            ReplySentMessage(
                payload=ReplySentPayload(ticket_id=str(self.ticket.id), receipt="ok")
            )
        )

        event = await AIResponseEvent.objects.filter(ticket_id=self.ticket.id).afirst()
        assert event is not None
        assert event.visibility == Visibility.PUBLIC
