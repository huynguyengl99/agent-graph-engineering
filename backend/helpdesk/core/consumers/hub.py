from typing import Any, ClassVar

from rest_framework.permissions import IsAuthenticated

from chanx.channels.authenticator import DjangoAuthenticator
from chanx.channels.websocket import AsyncJsonWebsocketConsumer
from chanx.core.decorators import channel, ws_handler
from chanx.core.topic import Topic
from chanx.messages.incoming import PingMessage
from chanx.messages.outgoing import PongMessage

from helpdesk.tickets.topics.team_topic import TicketTeamTopic
from helpdesk.tickets.topics.ticket_topic import TicketTopic


class HubAuthenticator(DjangoAuthenticator):
    """The socket authenticates the way the REST API does, with DRF's own
    classes, so one identity covers both."""

    permission_classes = [IsAuthenticated]


@channel(
    name="hub",
    description="One connection, many subscriptions: a ticket, and the team's half of it",
    tags=["realtime"],
)
class HubConsumer(AsyncJsonWebsocketConsumer):
    """A single socket per browser tab.

    A rep watching three tickets used to mean three sockets and three
    authentication round-trips. Topics multiplex them, and publishing no longer
    needs a consumer instance: `Topic.broadcast` is a classmethod, so a
    background task can reach subscribers directly.
    """

    topics: ClassVar[list[type[Topic[Any]]]] = [TicketTopic, TicketTeamTopic]
    authenticator_class = HubAuthenticator
    authenticator: HubAuthenticator

    async def post_authentication(self) -> None:
        """Topics read `scope["user"]`, which the authenticator does not set."""
        self.scope["user"] = self.authenticator.user

    @ws_handler
    async def handle_ping(self, _message: PingMessage) -> PongMessage:
        return PongMessage()
