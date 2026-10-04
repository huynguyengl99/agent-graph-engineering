from typing import Any, ClassVar

from chanx.channels.websocket import AsyncJsonWebsocketConsumer
from chanx.core.decorators import channel, ws_handler
from chanx.core.topic import Topic
from chanx.messages.incoming import PingMessage
from chanx.messages.outgoing import PongMessage

from helpdesk.tickets.topics.ticket_topic import TicketTopic


@channel(
    name="hub",
    description="One connection, many subscriptions: a topic per ticket",
    tags=["realtime"],
)
class HubConsumer(AsyncJsonWebsocketConsumer):
    """A single socket per browser tab.

    A rep watching three tickets used to mean three sockets and three
    authentication round-trips. Topics multiplex them, and publishing no longer
    needs a consumer instance: `Topic.broadcast` is a classmethod, so a
    background task can reach subscribers directly.
    """

    topics: ClassVar[list[type[Topic[Any]]]] = [TicketTopic]

    @ws_handler
    async def handle_ping(self, _message: PingMessage) -> PongMessage:
        return PongMessage()
