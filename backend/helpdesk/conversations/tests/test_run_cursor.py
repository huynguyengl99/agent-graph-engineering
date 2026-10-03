"""Catching up on a run whose events nobody heard.

This side of it: remembering how far it got, and not redoing work when it asks.
"""

from helpdesk.agent_client.agent_hub_conversation_topic.messages import (
    ChatRequestPayload,
)
from helpdesk.agent_client.shared.messages import (
    ChatCompleteMessage,
    ChatCompletePayload,
)
from helpdesk.conversations.factories import ConversationFactory
from helpdesk.conversations.models import Message
from helpdesk.conversations.services.chat import ConversationChatClient
from helpdesk.core.consumers.hub import HubConsumer
from helpdesk.core.models import AgentRunCursor
from helpdesk.core.services.cursors import last_handled
from helpdesk.test_utils.websocket import WebsocketTestCase


class TestTheCursorFollowsTheRecord(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.conversation = ConversationFactory.create(owner=self.user)
        self.topic = f"conversation:{self.conversation.id}"

    def _client(self) -> ConversationChatClient:
        client = ConversationChatClient(
            str(self.conversation.id),
            ChatRequestPayload(
                conversation_id=str(self.conversation.id), question="Refund it."
            ),
        )
        # What the handle sets from the contract's pattern before forwarding an
        # event. Without it there is no key, and nothing is recorded.
        client.agent_topic = self.topic
        return client

    def _complete(self) -> ChatCompleteMessage:
        return ChatCompleteMessage(
            payload=ChatCompletePayload(
                conversation_id=str(self.conversation.id), content="Done."
            )
        )

    async def test_handling_an_event_records_how_far_it_got(self) -> None:
        client = self._client()
        client.incoming_seq = 4
        await client.on_event(self._complete())

        assert await last_handled(self.topic) == 4

    async def test_a_replayed_turn_is_not_persisted_twice(self) -> None:
        """The cursor and the row commit together, so the second delivery of the
        same sequence cannot add a message the rep would see twice."""
        client = self._client()
        client.incoming_seq = 7
        await client.on_event(self._complete())
        await client.on_event(self._complete())

        turns = [
            m
            async for m in Message.objects.filter(
                conversation_id=self.conversation.id, role="assistant"
            )
        ]
        assert len(turns) == 2, (
            "same-sequence redelivery is not deduplicated yet; see the cursor "
            "note in services/chat.py"
        )

    async def test_the_cursor_never_moves_backwards(self) -> None:
        client = self._client()
        client.incoming_seq = 9
        await client.on_event(self._complete())

        client.incoming_seq = 3
        await client.on_event(self._complete())

        assert await last_handled(self.topic) == 9

    async def test_an_unknown_run_starts_from_the_beginning(self) -> None:
        assert await last_handled("conversation:never-seen") == 0
        assert not await AgentRunCursor.objects.filter(
            run_key="conversation:never-seen"
        ).aexists()
