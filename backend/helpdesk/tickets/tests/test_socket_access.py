"""Who a socket lets in, and which feeds it may then watch."""

from django.conf import settings

from helpdesk.accounts.factories import UserFactory
from helpdesk.hub.consumer import HubConsumer
from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory


class TestSocketAccess(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.mine = TicketFactory.create(created_by=self.user)
        self.someone_elses = TicketFactory.create(created_by=UserFactory.create())

    async def test_a_socket_without_the_login_cookie_is_refused(self) -> None:
        origins = settings.WEBSOCKET_ALLOWED_ORIGINS
        origin = origins[0] if origins and origins[0] != "*" else "http://localhost"
        anonymous = self.create_communicator(headers=[(b"origin", origin.encode())])
        await anonymous.connect()

        auth = await anonymous.wait_for_auth()

        assert auth is not None and auth.payload.status_code == 401
        await anonymous.assert_closed()

    async def test_a_customer_watches_their_own_ticket(self) -> None:
        reply = await self.subscribe_ready(f"ticket:{self.mine.id}")

        assert reply["action"] == "subscribed"

    async def test_a_customer_cannot_watch_someone_elses(self) -> None:
        reply = await self.subscribe_ready(f"ticket:{self.someone_elses.id}")

        assert reply["action"] != "subscribed"

    async def test_the_team_feed_needs_staff(self) -> None:
        """It carries reasoning, tool arguments and approval requests."""
        reply = await self.subscribe_ready(f"ticket:{self.mine.id}:team")

        assert reply["action"] != "subscribed"

    async def test_staff_watch_any_ticket_and_its_team_feed(self) -> None:
        self.user.is_staff = True
        await self.user.asave(update_fields=["is_staff"])

        communicator = await self.connect_ok()
        assert (await communicator.subscribe(f"ticket:{self.someone_elses.id}"))[
            "action"
        ] == "subscribed"
        assert (await communicator.subscribe(f"ticket:{self.someone_elses.id}:team"))[
            "action"
        ] == "subscribed"
