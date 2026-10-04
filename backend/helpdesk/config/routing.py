from channels.routing import URLRouter

from chanx.channels.routing import path

from helpdesk.core.consumers.hub import HubConsumer

# One socket per tab. A ticket is a topic on it, addressed
# per frame, so watching four resources no longer means four connections.
router = URLRouter(
    [
        path("ws/", HubConsumer.as_asgi()),
    ]
)
