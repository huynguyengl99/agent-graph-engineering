from typing import Any
from unittest.mock import patch

from channels.db import database_sync_to_async

from chanx.messages.incoming import PingMessage
from chanx.messages.outgoing import PongMessage

from helpdesk.conversations.factories import ConversationFactory
from helpdesk.conversations.messages import AskMessage, AskPayload
from helpdesk.conversations.models import Conversation, Message
from helpdesk.core.consumers.hub import HubConsumer
from helpdesk.test_utils.auth_api_test_case import AuthAPITestCase
from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory


class TestConversationTopic(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.conversation = ConversationFactory.create(owner=self.user)
        self.topic = f"conversation:{self.conversation.id}"

    async def test_connect_and_ping(self) -> None:
        await self.subscribe_ready(self.topic)
        await self.auth_communicator.send_message(PingMessage())

        assert await self.auth_communicator.receive_all_messages() == [PongMessage()]

    async def test_someone_elses_conversation_is_refused(self) -> None:
        other = await database_sync_to_async(ConversationFactory.create)()

        await self.auth_communicator.connect()
        reply = await self.auth_communicator.subscribe(f"conversation:{other.id}")

        assert reply["action"] != "subscribed"

    async def test_asking_persists_the_reps_turn_before_the_agent_replies(
        self,
    ) -> None:
        """The question is saved even if the agent never answers.

        `ask` is patched at the agent boundary, so this covers the backend's
        half without a live agent service.
        """
        sent: list[tuple[str, str]] = []

        async def fake_ask(
            conversation_id: str, question: str, *_args: Any, **_kwargs: Any
        ) -> None:
            sent.append((conversation_id, question))

        await self.subscribe_ready(self.topic)
        with patch(
            "helpdesk.conversations.services.chat.ask", fake_ask
        ):
            await self.auth_communicator.send_message(
                AskMessage(payload=AskPayload(content="What do I tell them?")),
                topic=self.topic,
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


class TestConversationApi(AuthAPITestCase):
    """The create response has to match what the schema promises.

    The generated client validates it, so returning only the create fields
    fails in the browser while every backend test still passes.
    """

    def test_create_returns_the_full_representation(self) -> None:
        response = self.auth_client.post(
            "/api/conversations/", {"title": "About the double charge"}, format="json"
        )

        assert response.status_code == 201
        # The rendered body, not response.data: camelization happens at render
        # time, and the rendered shape is what the generated client validates.
        assert set(response.json()) >= {
            "id",
            "title",
            "ticket",
            "createdAt",
            "updatedAt",
        }

    def test_a_conversation_can_name_its_ticket(self) -> None:
        ticket = TicketFactory.create(created_by=self.user)

        response = self.auth_client.post(
            "/api/conversations/",
            {"title": ticket.title, "ticket": str(ticket.id)},
            format="json",
        )

        assert response.status_code == 201
        assert response.json()["ticket"] == str(ticket.id)

    def test_only_your_own_conversations_are_listed(self) -> None:
        ConversationFactory.create(owner=self.user)
        ConversationFactory.create()

        response = self.auth_client.get("/api/conversations/")

        assert response.status_code == 200
        assert response.json()["count"] == 1
