"""A drafted reply parked at the gate, and what the ticket records when it is
sent. Both used to depend on state that did not outlive the socket."""

from unittest.mock import patch

from helpdesk.agent_client.triage.messages import (
    ApprovalRequiredMessage,
    ApprovalRequiredPayload,
    ReplySentMessage,
    ReplySentPayload,
    TriageRequestPayload,
)
from helpdesk.core.consumers.hub import HubConsumer
from helpdesk.test_utils.auth_api_test_case import AuthAPITestCase
from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.models import AIResponseEvent, PendingReply
from helpdesk.tickets.services.triage import TicketTriageClient, submit_approval

DRAFT = "Per [kb-002], the extra line is proration."


class TestPendingReply(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user)

    def client_for_ticket(self) -> TicketTriageClient:
        return TicketTriageClient(
            str(self.ticket.id),
            TriageRequestPayload(
                ticket_id=str(self.ticket.id), title="x", description="y"
            ),
        )

    async def park(self) -> None:
        await self.subscribe_ready(f"ticket:{self.ticket.id}")
        await self.client_for_ticket().handle_message(
            ApprovalRequiredMessage(
                payload=ApprovalRequiredPayload(
                    ticket_id=str(self.ticket.id),
                    draft=DRAFT,
                    findings=["No citation for the refund window."],
                )
            )
        )
        await self.auth_communicator.receive_all_json()

    async def _resume(self, content: str | None) -> None:
        async def fake_handle(client: TicketTriageClient) -> None:
            await client.handle_message(
                ReplySentMessage(
                    payload=ReplySentPayload(
                        ticket_id=str(self.ticket.id), receipt="sent"
                    )
                )
            )

        with patch(
            "helpdesk.tickets.services.triage.TicketTriageClient.handle", fake_handle
        ):
            await submit_approval(str(self.ticket.id), approved=True, content=content)

    async def test_the_draft_survives_a_reload(self) -> None:
        await self.park()

        pending = await PendingReply.objects.aget(ticket=self.ticket)

        assert pending.draft == DRAFT
        assert pending.findings == ["No citation for the refund window."]

    async def test_parking_persists_no_ticket_event(self) -> None:
        await self.park()

        assert not await AIResponseEvent.objects.filter(ticket=self.ticket).aexists()

    async def test_approving_without_editing_records_the_draft(self) -> None:
        """It recorded an empty event: `reply_sent` carries a receipt, not the
        text, and the browser sends no content when nothing was edited."""
        await self.park()
        await self._resume(None)

        event = await AIResponseEvent.objects.aget(ticket=self.ticket)

        assert event.content == DRAFT

    async def test_an_edited_reply_is_what_gets_recorded(self) -> None:
        await self.park()
        await self._resume("Rewritten by the reviewer.")

        event = await AIResponseEvent.objects.aget(ticket=self.ticket)

        assert event.content == "Rewritten by the reviewer."

    async def test_deciding_clears_the_card(self) -> None:
        await self.park()
        await self._resume(None)

        assert not await PendingReply.objects.filter(ticket=self.ticket).aexists()


class TestPendingReplyOnLoad(AuthAPITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user)

    def test_absent_when_nothing_is_waiting(self) -> None:
        body = self.auth_client.get(f"/api/tickets/{self.ticket.id}/").json()

        assert body["pendingReply"] is None

    def test_it_comes_back_in_the_shape_the_socket_sends(self) -> None:
        PendingReply.objects.create(
            ticket=self.ticket, draft=DRAFT, findings=["Missing citation."]
        )

        body = self.auth_client.get(f"/api/tickets/{self.ticket.id}/").json()

        assert body["pendingReply"]["draft"] == DRAFT
        assert body["pendingReply"]["findings"] == ["Missing citation."]
