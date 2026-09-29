from typing import Any, ClassVar

from chanx.channels.websocket import AsyncJsonWebsocketConsumer
from chanx.core.decorators import channel, ws_handler
from chanx.core.topic import Topic
from chanx.messages.incoming import PingMessage
from chanx.messages.outgoing import PongMessage

from helpdesk.conversations.topics.conversation_topic import ConversationTopic
from helpdesk.tickets.topics.ticket_topic import TicketTopic


@channel(
    name="hub",
    description="One connection, many subscriptions: tickets and conversations",
    tags=["realtime"],
)
class HubConsumer(AsyncJsonWebsocketConsumer):
    """A single socket per browser tab.

    A rep watching three tickets and a conversation used to mean four sockets
    and four authentication round-trips. Topics multiplex them, and publishing
    no longer needs a consumer instance: `Topic.broadcast` is a classmethod, so
    a background task can reach subscribers directly.
    """

    topics: ClassVar[list[type[Topic[Any]]]] = [TicketTopic, ConversationTopic]

    @ws_handler
    async def handle_ping(self, _message: PingMessage) -> PongMessage:
        return PongMessage()
