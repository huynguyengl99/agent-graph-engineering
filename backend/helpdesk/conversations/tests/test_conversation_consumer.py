from typing import Any
from unittest.mock import patch

from channels.db import database_sync_to_async

from chanx.messages.incoming import PingMessage
from chanx.messages.outgoing import PongMessage

from helpdesk.conversations.consumers import ConversationConsumer
from helpdesk.conversations.factories import ConversationFactory
from helpdesk.conversations.messages import AskMessage, AskPayload
from helpdesk.conversations.models import Conversation, Message
from helpdesk.test_utils.websocket import WebsocketTestCase


class TestConversationConsumer(WebsocketTestCase):
    consumer = ConversationConsumer

    def setUp(self) -> None:
        super().setUp()
        self.conversation = ConversationFactory.create(owner=self.user)
        self.ws_path = f"/ws/conversations/{self.conversation.id}/"

    async def test_connect_and_ping(self) -> None:
        await self.connect_ready()
        await self.auth_communicator.send_message(PingMessage())

        assert await self.auth_communicator.receive_all_messages() == [PongMessage()]

    async def test_someone_elses_conversation_is_refused(self) -> None:
        other = await database_sync_to_async(ConversationFactory.create)()
        self.ws_path = f"/ws/conversations/{other.id}/"

        await self.auth_communicator.connect()
        assert await self.auth_communicator.receive_nothing() is False

    async def test_asking_persists_the_reps_turn_before_the_agent_replies(
        self,
    ) -> None:
        """The question is saved even if the agent never answers.

        `ask` is patched at the agent boundary, so this covers the backend's
        half without a live agent service.
        """
        sent: list[tuple[str, str]] = []

        async def fake_ask(conversation_id: str, question: str, **_: Any) -> None:
            sent.append((conversation_id, question))

        await self.connect_ready()
        with patch(
            "helpdesk.conversations.consumers.conversation_consumer.ask", fake_ask
        ):
            await self.auth_communicator.send_message(
                AskMessage(payload=AskPayload(content="What do I tell them?"))
            )
            await self.auth_communicator.receive_all_messages()

        assert sent == [(str(self.conversation.id), "What do I tell them?")]

    async def test_a_conversation_can_be_opened_about_a_ticket(self) -> None:
        from helpdesk.tickets.factories import TicketFactory

        ticket = await database_sync_to_async(TicketFactory.create)(
            created_by=self.user
        )
        conversation = await database_sync_to_async(ConversationFactory.create)(
            owner=self.user, ticket=ticket
        )

        loaded = await database_sync_to_async(
            lambda: Conversation.objects.select_related("ticket").get(
                id=conversation.id
            )
        )()
        assert loaded.ticket is not None
        assert loaded.ticket.id == ticket.id

    async def test_messages_belong_to_their_conversation(self) -> None:
        await database_sync_to_async(Message.objects.create)(
            conversation=self.conversation, role="user", content="hello"
        )
        count = await Message.objects.filter(
            conversation=self.conversation
        ).acount()
        assert count == 1
