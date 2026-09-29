"""WebSocket test case utilities."""
from typing import Any

from django.conf import settings

from asgiref.sync import sync_to_async
from chanx.channels.testing import WebsocketTestCase as BaseWebsocketTestCase
from chanx.messages.incoming import PingMessage

from helpdesk.accounts.factories import UserFactory
from helpdesk.accounts.models import User


class WebsocketTestCase(BaseWebsocketTestCase):
    """Base test case for authenticated WebSocket tests.

    The socket carries the same JWT cookie auth_kit issues at login, so
    `scope["user"]` is the test user rather than AnonymousUser.
    """

    def setUp(self) -> None:
        self.user, self.ws_headers = self.create_user_and_ws_headers()
        super().setUp()

    def create_user_and_ws_headers(self) -> tuple[User, list[tuple[bytes, bytes]]]:
        from auth_kit.app_settings import auth_kit_settings
        from rest_framework_simplejwt.tokens import AccessToken

        user = UserFactory.create()

        origins = settings.WEBSOCKET_ALLOWED_ORIGINS
        origin = origins[0] if origins and origins[0] != "*" else "http://localhost"
        cookie = f"{auth_kit_settings.AUTH_JWT_COOKIE_NAME}={AccessToken.for_user(user)}"
        ws_headers = [
            (b"origin", origin.encode()),
            (b"x-forwarded-for", b"127.0.0.1"),
            (b"cookie", cookie.encode()),
        ]
        return user, ws_headers

    async def acreate_user_and_ws_headers(
        self,
    ) -> tuple[User, list[tuple[bytes, bytes]]]:
        return await sync_to_async(self.create_user_and_ws_headers)()

    def get_ws_headers(self) -> list[tuple[bytes, bytes]]:
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
