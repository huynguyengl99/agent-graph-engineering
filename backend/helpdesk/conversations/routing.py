from channels.routing import URLRouter

from chanx.channels.routing import path

from helpdesk.conversations.consumers.conversation_consumer import (
    ConversationConsumer,
)

router = URLRouter(
    [
        path("<uuid:conversation_id>/", ConversationConsumer.as_asgi()),
    ]
)
