from channels.routing import URLRouter

from chanx.channels.routing import path

from helpdesk.tickets.consumers.ticket_consumer import TicketConsumer

router = URLRouter(
    [
        path("<uuid:ticket_id>/", TicketConsumer.as_asgi()),
    ]
)
