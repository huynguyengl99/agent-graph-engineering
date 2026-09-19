from channels.routing import URLRouter

from chanx.channels.routing import include, path

ws_router = URLRouter(
    [
        path("tickets/", include("helpdesk.tickets.routing")),
    ]
)

router = URLRouter(
    [
        path("ws/", include(ws_router)),
    ]
)
