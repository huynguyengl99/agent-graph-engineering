"""WebSocket test case utilities."""
from typing import Any

from django.conf import settings

from asgiref.sync import sync_to_async
from chanx.channels.testing import WebsocketTestCase as BaseWebsocketTestCase
from chanx.messages.incoming import PingMessage

from helpdesk.accounts.factories import UserFactory
from helpdesk.accounts.models import User


class WebsocketTestCase(BaseWebsocketTestCase):
    """
    Base test case for WebSocket tests with authentication.

    Automatically creates a test user and WebSocket headers with session cookie.
    """

    def setUp(self) -> None:
        """Set up test user and WebSocket headers."""
        self.user, self.ws_headers = self.create_user_and_ws_headers()
        super().setUp()

    def create_user_and_ws_headers(self) -> tuple[User, list[tuple[bytes, bytes]]]:
        """
        Create a test user and WebSocket headers with authentication.

        Returns:
            Tuple of (user, websocket_headers)
        """
        user = UserFactory.create()

        origins = settings.WEBSOCKET_ALLOWED_ORIGINS
        origin = origins[0] if origins and origins[0] != "*" else "http://localhost"
        ws_headers = [
            (b"origin", origin.encode()),
            (b"x-forwarded-for", b"127.0.0.1"),
        ]
        return user, ws_headers

    async def acreate_user_and_ws_headers(
        self,
    ) -> tuple[User, list[tuple[bytes, bytes]]]:
        """Async version of create_user_and_ws_headers."""
        return await sync_to_async(self.create_user_and_ws_headers)()

    def get_ws_headers(self) -> list[tuple[bytes, bytes]]:
        """Get the WebSocket headers for this test."""
        return self.ws_headers

    async def connect_ready(self, communicator: Any = None) -> Any:
        """Connect, and wait until the consumer has finished joining its groups.

        chanx accepts the socket before `post_authentication` runs, so a plain
        `connect()` can return while `group_add` is still pending. Any broadcast
        sent in that window goes to an empty group and the test sees nothing.
        Round-tripping a ping proves the consumer has processed at least one
        message, which means `post_authentication` has completed.
        """
        communicator = communicator or self.auth_communicator
        await communicator.connect()
        await communicator.send_message(PingMessage())
        await communicator.receive_all_messages()
        return communicator
