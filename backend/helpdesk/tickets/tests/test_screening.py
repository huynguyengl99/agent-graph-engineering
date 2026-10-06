"""What the agent wrote, checked once more where the audience is settled."""

from typing import Any

from helpdesk.hub.consumer import HubConsumer
from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.models import Visibility
from helpdesk.tickets.services.screening import withheld


class TestWhatStopsIt:
    def test_a_credential_shape(self) -> None:
        # An `sk-ant-` key is also an `sk-` key, so both say so. Being named
        # twice is not a problem; being named at all is the point.
        assert "anthropic_key" in withheld(
            "use sk-ant-0123456789abcdef0123", ticket_id="t"
        )

    def test_another_record_s_id(self) -> None:
        assert withheld(
            "see 11111111-2222-3333-4444-555555555555",
            ticket_id="99999999-2222-3333-4444-555555555555",
        ) == ["cross_ticket_reference"]

    def test_its_own_ticket_is_not_another_record(self) -> None:
        same = "11111111-2222-3333-4444-555555555555"
        assert withheld(f"this ticket {same}", ticket_id=same) == []

    def test_ordinary_prose_passes(self) -> None:
        assert withheld("Two charges of 29.00 on one plan.", ticket_id="t") == []


class TestNothingUnscreenedReachesThem(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user)

    async def _customer_sees(self, content: str) -> list[Any]:
        from helpdesk.tickets.services.support import TicketSink

        await self.subscribe_ready(f"ticket:{self.ticket.id}")
        sink = TicketSink(str(self.ticket.id), Visibility.PUBLIC)
        await sink.token(content)
        frames = await self.auth_communicator.receive_all_json(timeout=2)
        return [f for f in frames if f.get("action") == "answer_streaming"]

    async def test_a_reply_naming_a_credential_is_held_back(self) -> None:
        assert (
            await self._customer_sees("Your key is sk-ant-0123456789abcdef0123") == []
        )

    async def test_an_ordinary_reply_goes_through(self) -> None:
        assert len(await self._customer_sees("Looking into the duplicate charge.")) == 1
