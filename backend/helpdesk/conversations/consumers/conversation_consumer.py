import asyncio

from channels.db import database_sync_to_async

from chanx.channels.websocket import AsyncJsonWebsocketConsumer
from chanx.core.decorators import channel, ws_handler
from chanx.messages.incoming import PingMessage
from chanx.messages.outgoing import PongMessage

from helpdesk.conversations.messages import (
    AskMessage,
    AssistantDoneMessage,
    ChatErrorMessage,
    ChatMessageMessage,
    DraftToTicketMessage,
    TokenMessage,
)
from helpdesk.conversations.models import Conversation
from helpdesk.conversations.services.chat import ask, conversation_group
from helpdesk.tickets.services.triage import submit_approval


@channel(
    name="conversations",
    description="A support agent's live conversation with the assistant",
    tags=["conversations", "realtime"],
)
class ConversationConsumer(AsyncJsonWebsocketConsumer):
    """One socket per conversation. Internal: nothing sent here is customer-visible."""

    async def post_authentication(self) -> None:
        assert self.channel_layer
        self.conversation_id: str = str(
            self.scope["url_route"]["kwargs"]["conversation_id"]
        )

        if not await self._owns_conversation(self.conversation_id):
            await self.close()
            return

        self.group_name = conversation_group(self.conversation_id)
        self.groups.append(self.group_name)
        await self.channel_layer.group_add(self.group_name, self.channel_name)

    @ws_handler
    async def handle_ping(self, _message: PingMessage) -> PongMessage:
        return PongMessage()

    @ws_handler(
        summary="Ask the assistant",
        description="Streams the answer back token by token, then persists it.",
        output_type=(
            ChatMessageMessage | TokenMessage | AssistantDoneMessage | ChatErrorMessage
        ),
    )
    async def handle_ask(self, message: AskMessage) -> None:
        # Detached: the answer streams over the group, not this return path.
        self._ask_task = asyncio.create_task(
            ask(self.conversation_id, message.payload.content)
        )

    @ws_handler(
        summary="Send a drafted reply to a ticket",
        description=(
            "The one path out of the conversation. It resumes the ticket's "
            "triage run at its approval gate, so the customer-facing send is "
            "still gated."
        ),
        output_type=ChatErrorMessage,
    )
    async def handle_draft_to_ticket(self, message: DraftToTicketMessage) -> None:
        payload = message.payload
        self._draft_task = asyncio.create_task(
            submit_approval(
                ticket_id=payload.ticket_id, approved=True, content=payload.content
            )
        )

    @database_sync_to_async
    def _owns_conversation(self, conversation_id: str) -> bool:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            return False
        return Conversation.objects.filter(
            id=conversation_id, owner=user
        ).exists()
