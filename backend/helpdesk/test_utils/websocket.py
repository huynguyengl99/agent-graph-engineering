"""WebSocket test case utilities."""

import asyncio
from typing import Annotated, Any

from django.conf import settings

from asgiref.sync import sync_to_async
from chanx.channels.testing import WebsocketTestCase as BaseWebsocketTestCase
from chanx.constants import COMPLETE_ACTIONS
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
        cookie = (
            f"{auth_kit_settings.AUTH_JWT_COOKIE_NAME}={AccessToken.for_user(user)}"
        )
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

    async def receive_topic_messages(
        self,
        union: Any,
        *,
        stop_action: str | None = None,
        timeout: float = 3,
    ) -> list[Any]:
        """Read one fan-out and parse it against a topic's output union.

        `receive_all_messages` validates against the *consumer's* outgoing
        union, and a hub consumer declares only its own handlers, so a topic's
        frames do not parse there.

        Reads frame by frame and stops at the first terminator, so two
        broadcasts in a row are drained one at a time. A topic fan-out ends
        with `event_complete`, not the `group_complete` a consumer sends.
        """
        import humps
        from pydantic import Field, TypeAdapter

        adapter: TypeAdapter[Any] = TypeAdapter(
            Annotated[union, Field(discriminator="action")]
        )
        messages: list[Any] = []
        try:
            async with asyncio.timeout(timeout):
                while True:
                    frame = humps.decamelize(
                        await self.auth_communicator.receive_json_from(timeout)
                    )
                    action = frame.get("action")
                    if action not in COMPLETE_ACTIONS:
                        # Envelope fields are transport, not part of the model.
                        messages.append(
                            adapter.validate_python(
                                {
                                    k: v
                                    for k, v in frame.items()
                                    if k not in ("topic", "version", "ref")
                                }
                            )
                        )
                    if action in COMPLETE_ACTIONS and (
                        stop_action is None or action == stop_action
                    ):
                        break
        except (TimeoutError, asyncio.CancelledError):
            pass
        return messages

    async def connect_ok(self, communicator: Any = None) -> Any:
        """Connect and read the frame chanx sends with the DRF auth result.

        It is not part of the consumer's outgoing union, so leaving it in the
        buffer makes the next read fail to parse.
        """
        communicator = communicator or self.auth_communicator
        await communicator.connect()
        await communicator.assert_authenticated_status_ok()
        return communicator

    async def subscribe_ready(self, topic: str, communicator: Any = None) -> Any:
        """Connect and join a topic, ready to receive its broadcasts.

        Subscribing is itself a round-trip, so its reply also proves the
        consumer has finished joining the group.
        """
        communicator = await self.connect_ok(communicator)
        return await communicator.subscribe(topic)

    async def connect_ready(self, communicator: Any = None) -> Any:
        """Connect, and wait until the consumer has finished joining its groups.

        chanx accepts the socket before `post_authentication` runs, so a plain
        `connect()` can return while `group_add` is still pending. Any broadcast
        sent in that window goes to an empty group and the test sees nothing.
        Round-tripping a ping proves the consumer has processed at least one
        message, which means `post_authentication` has completed.
        """
        communicator = await self.connect_ok(communicator)
        await communicator.send_message(PingMessage())
        await communicator.receive_all_messages()
        return communicator
