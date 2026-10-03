"""The backend half of the seam, with the agent stubbed at the client boundary.

A true cross-service test needs both processes up; that lives in the eval/smoke
scripts. Here the generated client is driven directly, which still exercises the
real message models, the real group envelope, and real persistence.
"""

from channels.db import database_sync_to_async

from helpdesk.agent_client.agent_hub_triage_topic.messages import (
    AnswerMessage,
    AnswerPayload,
    ApprovalRequiredMessage,
    ApprovalRequiredPayload,
    ClassifiedMessage,
    ClassifiedPayload,
    DecidedMessage,
    DecidedPayload,
    ReplySentMessage,
    ReplySentPayload,
    TriageErrorMessage,
    TriageErrorPayload,
    TriageRequestPayload,
)
from helpdesk.core.consumers.hub import HubConsumer
from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.models import AIResponseEvent
from helpdesk.tickets.services.triage import TicketTriageClient
from helpdesk.tickets.topics.ticket_topic import TicketFeedEvent


class TestTriageService(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        # A reviewer, not the requester: progress and drafts are the team's.
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.ticket = TicketFactory.create(created_by=self.user)
        self.topic = f"ticket:{self.ticket.id}"

    def client_for_ticket(self) -> TicketTriageClient:
        return TicketTriageClient(
            str(self.ticket.id),
            TriageRequestPayload(
                ticket_id=str(self.ticket.id),
                title=self.ticket.title,
                description=self.ticket.description,
            ),
        )

    async def test_a_draft_awaiting_approval_is_not_persisted(self) -> None:
        """Nothing reaches the ticket log until the reply is actually sent."""
        await self.subscribe_ready(self.topic)
        client = self.client_for_ticket()

        await client.on_event(
            AnswerMessage(
                payload=AnswerPayload(
                    ticket_id=str(self.ticket.id),
                    content="Per [kb-002], the extra line is proration.",
                    requires_approval=True,
                )
            )
        )

        assert await self._ai_response_count() == 0

    async def test_approval_request_reaches_the_reviewer(self) -> None:
        await self.subscribe_ready(self.topic)
        client = self.client_for_ticket()

        await client.on_event(
            ApprovalRequiredMessage(
                payload=ApprovalRequiredPayload(
                    ticket_id=str(self.ticket.id), draft="Draft reply."
                )
            )
        )

        messages = await self.receive_topic_messages(TicketFeedEvent)
        assert [m.action for m in messages] == ["approval_required"]
        assert messages[0].payload.draft == "Draft reply."
        assert await self._ai_response_count() == 0

    async def test_reply_is_persisted_only_once_it_is_sent(self) -> None:
        await self.subscribe_ready(self.topic)
        client = self.client_for_ticket()
        client.pending_reply = "Per [kb-002], the extra line is proration."

        await client.on_event(
            ReplySentMessage(
                payload=ReplySentPayload(
                    ticket_id=str(self.ticket.id), receipt="queued"
                )
            )
        )

        messages = await self.receive_topic_messages(TicketFeedEvent)
        assert [m.action for m in messages] == ["new_event"]
        assert messages[0].payload.event.event_type == "ai_response"
        assert await self._ai_response_count() == 1

    async def test_progress_stages_reach_the_group_without_persisting(self) -> None:
        await self.subscribe_ready(self.topic)
        client = self.client_for_ticket()

        # Each broadcast terminates with its own `group_complete`, so drain
        # one fan-out at a time rather than expecting them in a single read.
        await client.on_event(
            ClassifiedMessage(
                payload=ClassifiedPayload(
                    ticket_id=str(self.ticket.id),
                    category="billing",
                    priority="medium",
                    reasoning="Asks about an invoice.",
                )
            )
        )
        classified = await self.receive_topic_messages(TicketFeedEvent)

        await client.on_event(
            DecidedMessage(
                payload=DecidedPayload(
                    ticket_id=str(self.ticket.id),
                    decision="SearchKnowledgeBase",
                    reasoning="Documented policy.",
                )
            )
        )
        decided = await self.receive_topic_messages(TicketFeedEvent)

        stages = [
            m.payload.stage
            for m in [*classified, *decided]
            if m.action == "agent_progress"
        ]
        assert stages == ["classified", "decided"]

        # Progress is transient; only the final answer becomes a ticket event.
        assert await self._ai_response_count() == 0

    async def test_agent_failure_surfaces_to_the_client(self) -> None:
        await self.subscribe_ready(self.topic)
        client = self.client_for_ticket()

        await client.on_event(
            TriageErrorMessage(
                payload=TriageErrorPayload(
                    ticket_id=str(self.ticket.id),
                    message="The triage agent could not complete this ticket.",
                )
            )
        )

        messages = await self.receive_topic_messages(TicketFeedEvent)
        assert [m.payload.stage for m in messages] == ["failed"]

    @database_sync_to_async
    def _ai_response_count(self) -> int:
        return AIResponseEvent.objects.filter(ticket=self.ticket).count()
