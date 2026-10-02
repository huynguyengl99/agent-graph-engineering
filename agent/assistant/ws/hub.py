from typing import Any, ClassVar

from chanx.core.decorators import channel, ws_handler
from chanx.core.topic import Topic
from chanx.fast_channels.websocket import AsyncJsonWebsocketConsumer
from chanx.messages.incoming import PingMessage
from chanx.messages.outgoing import PongMessage

from assistant.core.layers import LAYER_ALIAS
from assistant.ws.topics import ConversationTopic, TriageTopic


@channel(
    name="agent",
    description="One connection from the backend, many runs",
    tags=["agent"],
)
class AgentHubConsumer(AsyncJsonWebsocketConsumer):
    """The backend's single socket into this service.

    One connection rather than one per run: a run belongs to its ticket or
    conversation, so a resume arrives on a subscription that is already open and
    a node can emit without the socket that started the run being the only thing
    that can hear it.
    """

    channel_layer_alias = LAYER_ALIAS
    topics: ClassVar[list[type[Topic[Any]]]] = [TriageTopic, ConversationTopic]

    @ws_handler
    async def handle_ping(self, _message: PingMessage) -> PongMessage:
        return PongMessage()
