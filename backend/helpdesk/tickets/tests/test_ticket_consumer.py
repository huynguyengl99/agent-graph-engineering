from typing import cast

from channels.db import database_sync_to_async

from chanx.messages.incoming import PingMessage
from chanx.messages.outgoing import PongMessage

from helpdesk.core.consumers.hub import HubConsumer
from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.messages import (
    NewEventMessage,
    SendMessageMessage,
    SendMessagePayload,
)
from helpdesk.tickets.models import CommentEvent
from helpdesk.tickets.topics.ticket_topic import TicketFeedEvent


class TestTicketTopic(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user)
        self.topic = f"ticket:{self.ticket.id}"

    async def test_connect_and_ping(self) -> None:
        await self.connect_ready()
        await self.auth_communicator.send_message(PingMessage())

        assert await self.auth_communicator.receive_all_messages() == [PongMessage()]

    async def test_comment_is_persisted_and_broadcast(self) -> None:
        await self.subscribe_ready(self.topic)
        await self.auth_communicator.send_message(
            SendMessageMessage(payload=SendMessagePayload(content="Still broken.")),
            topic=self.topic,
        )

        # The handler's own "complete" arrives before the topic fan-out, so
        # read through to the event terminator rather than the first one.
        messages = await self.receive_topic_messages(
            TicketFeedEvent, stop_action="event_complete"
        )

        assert len(messages) == 1
        new_event = cast(NewEventMessage, messages[0])
        assert new_event.action == "new_event"
        # chanx underscoreizes frames on parse, so the decoded payload is
        # snake_case here while the wire is camelCase (asserted below).
        assert new_event.payload.event.event_type == "comment"
        assert new_event.payload.event.content == "Still broken."

        assert await self._comment_count() == 1

    async def test_wire_payload_is_camel_case_like_the_rest_api(self) -> None:
        """The browser consumes REST and WebSocket with one generated type.

        REST goes through CamelCaseJSONRenderer; WebSocket payloads do not, so
        this asserts the raw frame rather than the parsed message.
        """
        await self.subscribe_ready(self.topic)
        await self.auth_communicator.send_message(
            SendMessageMessage(payload=SendMessagePayload(content="Still broken.")),
            topic=self.topic,
        )

        frames = await self.auth_communicator.receive_all_json(timeout=3)
        events = [f for f in frames if f.get("action") == "new_event"]

        assert len(events) == 1
        event = events[0]["payload"]["event"]
        assert event["eventType"] == "comment"
        assert "createdAt" in event
        assert "event_type" not in event

    async def test_an_unknown_ticket_cannot_be_subscribed(self) -> None:
        """One socket serves every ticket now, so a bad id refuses the
        subscription rather than closing the connection."""
        await self.auth_communicator.connect()
        reply = await self.auth_communicator.subscribe(
            "ticket:00000000-0000-0000-0000-000000000000"
        )

        assert reply["action"] != "subscribed"

    @database_sync_to_async
    def _comment_count(self) -> int:
        return CommentEvent.objects.filter(ticket=self.ticket).count()
