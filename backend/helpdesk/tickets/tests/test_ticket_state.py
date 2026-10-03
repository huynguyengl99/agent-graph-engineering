"""Where a ticket stands: graded by the agent, set by staff, read-only to the
person who reported it."""

from typing import Any

from helpdesk.core.consumers.hub import HubConsumer
from helpdesk.test_utils.auth_api_test_case import AuthAPITestCase
from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.messages import UpdateTicketMessage, UpdateTicketPayload
from helpdesk.tickets.models import StatusChangeEvent, Ticket
from helpdesk.tickets.services.status import set_priority, set_status


class TestTheAgentGradesIt(WebsocketTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user, priority="medium")

    async def test_its_reading_is_applied(self) -> None:
        moved = await set_priority(str(self.ticket.id), "urgent")

        assert moved
        assert (await Ticket.objects.aget(id=self.ticket.id)).priority == "urgent"

    async def test_agreeing_with_the_ticket_changes_nothing(self) -> None:
        assert not await set_priority(str(self.ticket.id), "medium")

    async def test_closing_it_leaves_a_record(self) -> None:
        event = await set_status(str(self.ticket.id), "resolved", self.user)

        assert event is not None
        assert event.old_status == "open"
        assert event.new_status == "resolved"
        assert await StatusChangeEvent.objects.filter(
            ticket_id=self.ticket.id
        ).aexists()


class TestOnlyStaffSetIt(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user, priority="low")
        self.topic = f"ticket:{self.ticket.id}"

    async def ask(self, **fields: str) -> list[dict[str, Any]]:
        await self.subscribe_ready(self.topic)
        await self.auth_communicator.send_message(
            UpdateTicketMessage(payload=UpdateTicketPayload(**fields)),
            topic=self.topic,
        )
        # Raw frames: the status event and the ticket's own fields arrive as
        # two broadcasts, so reading to the first terminator misses the second.
        return await self.auth_communicator.receive_all_json(timeout=3)

    async def test_the_requester_cannot_raise_their_own_priority(self) -> None:
        await self.ask(priority="urgent")

        assert (await Ticket.objects.aget(id=self.ticket.id)).priority == "low"

    async def test_staff_can(self) -> None:
        self.user.is_staff = True
        await self.user.asave(update_fields=["is_staff"])

        messages = await self.ask(priority="urgent", status="resolved")

        fresh = await Ticket.objects.aget(id=self.ticket.id)
        assert fresh.priority == "urgent"
        assert fresh.status == "resolved"
        updated = [f for f in messages if f.get("action") == "ticket_updated"]
        assert updated, "the header is told, or it keeps showing the old state"
        assert updated[-1]["payload"]["status"] == "resolved"


class TestTheApiAgrees(AuthAPITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user)

    def test_a_customer_patching_their_own_ticket_is_refused(self) -> None:
        """Scoping the queryset is not enough: it is their ticket."""
        response = self.auth_client.patch(
            f"/api/tickets/{self.ticket.id}/", {"status": "closed"}, format="json"
        )

        assert response.status_code == 403
        assert Ticket.objects.get(id=self.ticket.id).status == "open"

    def test_staff_may(self) -> None:
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

        response = self.auth_client.patch(
            f"/api/tickets/{self.ticket.id}/", {"status": "closed"}, format="json"
        )

        assert response.status_code == 200
        assert Ticket.objects.get(id=self.ticket.id).status == "closed"
