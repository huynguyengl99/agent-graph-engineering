"""Who answers a ticket, as it changes hands."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, patch

from channels.db import database_sync_to_async
from django.test import override_settings

from helpdesk.accounts.factories import UserFactory
from helpdesk.agent_client.agent_hub_conversation_topic.messages import (
    ChatCompleteMessage,
    ChatCompletePayload,
    ChatRequestPayload,
    ToolApprovalMessage,
    ToolApprovalPayload,
)
from helpdesk.agent_client.agent_hub_triage_topic.messages import (
    ApprovalRequiredMessage,
    ApprovalRequiredPayload,
    ReplySentMessage,
    ReplySentPayload,
    TriageErrorMessage,
    TriageErrorPayload,
    TriageRequestPayload,
)
from helpdesk.core.consumers.hub import HubConsumer
from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.messages import (
    AgentProgressMessage,
    AgentProgressPayload,
    NewEventMessage,
    NewEventPayload,
    SendMessageMessage,
    SendMessagePayload,
    SetAgentMessage,
    SetAgentPayload,
)
from helpdesk.tickets.models import (
    AIResponseEvent,
    CommentEvent,
    Handling,
    PendingToolCall,
    Ticket,
    Visibility,
)
from helpdesk.tickets.serializers.event import serialize_event
from helpdesk.tickets.services.consult import TicketConsultClient
from helpdesk.tickets.services.handoff import hand_off, handling_of
from helpdesk.tickets.services.triage import TicketTriageClient, _parked_visibility
from helpdesk.tickets.topics.ticket_topic import TicketFeedEvent, TicketTopic


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

    async def test_the_customer_is_told_who_has_it(self) -> None:
        """Being handed between an assistant and a person is the customer's
        business; why they were is not."""
        event = await hand_off(
            str(self.ticket.id), Handling.NEEDS_HUMAN, reason="Needs billing access"
        )

        assert event is not None
        assert event.visibility == "public"


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
            SetAgentMessage(payload=SetAgentPayload(on=True, reason="Resolved")),
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


class TestTheCustomerOnlySeesTheirHalf(WebsocketTestCase):
    """The REST list filters by visibility; the live fan-out has to as well, or
    an internal note reaches whoever has the ticket open."""

    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        self.ticket = TicketFactory.create(created_by=self.user)
        self.topic = f"ticket:{self.ticket.id}"

    async def test_an_internal_note_is_not_relayed(self) -> None:
        await self.subscribe_ready(self.topic)
        staff = await UserFactory.acreate(is_staff=True)

        event = await database_sync_to_async(CommentEvent.objects.create)(
            ticket_id=self.ticket.id,
            content="Check whether the second charge cleared.",
            created_by=staff,
            visibility=Visibility.INTERNAL,
        )
        await TicketTopic.broadcast(
            self.topic,
            NewEventMessage(
                payload=NewEventPayload(
                    event=await database_sync_to_async(serialize_event)(event)
                )
            ),
        )

        messages = await self.receive_topic_messages(
            TicketFeedEvent, stop_action="event_complete"
        )
        assert messages == []

    async def test_a_handoff_arrives_without_its_reason(self) -> None:
        """They are told a person took over, not that the agent could not do it."""
        await self.subscribe_ready(self.topic)

        event = await hand_off(
            str(self.ticket.id), Handling.NEEDS_HUMAN, reason="Needs billing access"
        )
        assert event is not None
        await TicketTopic.broadcast(
            self.topic, NewEventMessage(payload=NewEventPayload(event=event))
        )

        [message] = await self.receive_topic_messages(
            TicketFeedEvent, stop_action="event_complete"
        )
        relayed = cast(NewEventMessage, message).payload.event
        assert relayed.event_type == "handoff"
        assert relayed.reason == ""

    async def test_the_agents_progress_is_not_relayed(self) -> None:
        await self.subscribe_ready(self.topic)

        await TicketTopic.broadcast(
            self.topic,
            AgentProgressMessage(
                payload=AgentProgressPayload(stage="decided", detail="Escalate")
            ),
        )

        messages = await self.receive_topic_messages(
            TicketFeedEvent, stop_action="event_complete"
        )
        assert messages == []


class TestAFailedRunDoesNotStrandTheCustomer(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user)

    async def test_the_ticket_goes_to_a_person(self) -> None:
        await self.subscribe_ready(f"ticket:{self.ticket.id}")
        client = TicketTriageClient(
            str(self.ticket.id),
            TriageRequestPayload(
                ticket_id=str(self.ticket.id), title="x", description="y"
            ),
        )

        await client.on_event(
            TriageErrorMessage(
                payload=TriageErrorPayload(
                    ticket_id=str(self.ticket.id), message="The run died."
                )
            )
        )

        assert await handling_of(str(self.ticket.id)) == Handling.NEEDS_HUMAN


class TestTheGateOnTheTicket(WebsocketTestCase):
    """The tool the agent proposes while helping the team is approved here, and
    what it writes afterwards goes where the reviewer said."""

    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.ticket = TicketFactory.create(created_by=self.user)
        self.topic = f"ticket:{self.ticket.id}"

    def client_for(self, visibility: str = Visibility.INTERNAL) -> TicketConsultClient:
        return TicketConsultClient(
            str(self.ticket.id),
            ChatRequestPayload(conversation_id=str(self.ticket.id), question="refund?"),
            visibility=visibility,
        )

    async def propose(self) -> None:
        await self.client_for().on_event(
            ToolApprovalMessage(
                payload=ToolApprovalPayload(
                    conversation_id=str(self.ticket.id),
                    tool="issue_refund",
                    description="Refund a charge",
                    arguments={"amount": 29.0},
                    arguments_schema={"properties": {"amount": {"type": "number"}}},
                )
            )
        )

    async def test_a_proposal_survives_a_reload(self) -> None:
        await self.subscribe_ready(self.topic)

        await self.propose()

        parked = await PendingToolCall.objects.aget(ticket_id=self.ticket.id)
        assert parked.tool == "issue_refund"
        assert parked.arguments == {"amount": 29.0}

    async def test_a_proposal_persists_no_ticket_event(self) -> None:
        """Proposing is not answering."""
        await self.subscribe_ready(self.topic)

        await self.propose()

        assert not await AIResponseEvent.objects.filter(
            ticket_id=self.ticket.id
        ).aexists()

    async def test_the_reviewer_can_send_the_result_to_the_customer(self) -> None:
        await self.subscribe_ready(self.topic)

        await self.client_for(Visibility.PUBLIC).on_event(
            ChatCompleteMessage(
                payload=ChatCompletePayload(
                    conversation_id=str(self.ticket.id),
                    content="Your refund of $29.00 is on its way.",
                )
            )
        )

        event = await AIResponseEvent.objects.filter(ticket_id=self.ticket.id).afirst()
        assert event is not None
        assert event.visibility == Visibility.PUBLIC

    async def test_a_lookup_stays_with_the_team(self) -> None:
        await self.subscribe_ready(self.topic)

        await self.client_for().on_event(
            ChatCompleteMessage(
                payload=ChatCompletePayload(
                    conversation_id=str(self.ticket.id),
                    content="They are on the monthly plan.",
                )
            )
        )

        event = await AIResponseEvent.objects.filter(ticket_id=self.ticket.id).afirst()
        assert event is not None
        assert event.visibility == Visibility.INTERNAL
