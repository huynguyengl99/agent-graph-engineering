"""Drive the assistant for one conversation turn.

Unlike triage, nothing here is gated: the rep is the only audience, so the
answer is persisted and broadcast as soon as it finishes. A reply only becomes
irreversible when it is handed to a ticket, which goes through the tickets
channel and its approval gate.
"""

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings

import structlog
from chanx.messages.base import BaseMessage

from helpdesk.agent_client.chat.client import ChatClient
from helpdesk.agent_client.chat.messages import (
    ChatCompleteMessage,
    ChatErrorMessage,
    ChatRequestMessage,
    ChatRequestPayload,
    ChatTicket,
    ChatTokenMessage,
    ChatTurn,
    IncomingMessage,
)
from helpdesk.conversations.messages import (
    AssistantDoneMessage,
    AssistantDonePayload,
    ChatMessageMessage,
    ChatMessagePayload,
    TokenMessage,
    TokenPayload,
)
from helpdesk.conversations.messages import (
    ChatErrorMessage as FEChatErrorMessage,
)
from helpdesk.conversations.messages import (
    ChatErrorPayload as FEChatErrorPayload,
)
from helpdesk.conversations.models import Conversation, Message, MessageRole

logger = structlog.get_logger(__name__)


def conversation_group(conversation_id: str) -> str:
    return f"conversation_{conversation_id}"


async def broadcast(group: str, message: BaseMessage) -> None:
    """Send to a group without owning a consumer.

    Mirrors the envelope `AsyncJsonWebsocketConsumer.broadcast_message` uses.
    `from_channel` is empty because there is no originating socket to exclude.
    """
    channel_layer = get_channel_layer()
    assert channel_layer
    await channel_layer.group_send(
        group,
        {
            "type": "handle_group_message",
            "message": message.model_dump(mode="json"),
            "exclude_current": False,
            "from_channel": "",
        },
    )


class ConversationChatClient(ChatClient):
    """One turn, then disconnect."""

    def __init__(self, conversation_id: str, request: ChatRequestPayload) -> None:
        super().__init__(settings.AGENT_WS_URL)
        self.conversation_id = conversation_id
        self.request = request
        self.group = conversation_group(conversation_id)
        self.answer = ""

    async def send_init_message(self) -> None:
        await self.send_message(ChatRequestMessage(payload=self.request))

    async def disconnect(self, code: int = 1000, reason: str = "") -> None:
        if getattr(self, "websocket", None) is None:
            return
        await super().disconnect(code, reason)

    async def handle_message(self, message: IncomingMessage) -> None:
        match message:
            case ChatTokenMessage(payload=payload):
                await broadcast(
                    self.group,
                    TokenMessage(payload=TokenPayload(delta=payload.delta)),
                )
            case ChatCompleteMessage(payload=payload):
                self.answer = payload.content
                await self._persist_answer(payload.content)
                await self.disconnect()
            case ChatErrorMessage(payload=payload):
                await broadcast(
                    self.group,
                    FEChatErrorMessage(
                        payload=FEChatErrorPayload(detail=payload.message)
                    ),
                )
                await self.disconnect()

    async def _persist_answer(self, content: str) -> None:
        message = await self._create_message(
            self.conversation_id, MessageRole.ASSISTANT, content
        )
        await broadcast(
            self.group,
            AssistantDoneMessage(
                payload=AssistantDonePayload(
                    message_id=str(message.id), content=content
                )
            ),
        )

    @database_sync_to_async
    def _create_message(
        self, conversation_id: str, role: str, content: str
    ) -> Message:
        return Message.objects.create(
            conversation_id=conversation_id, role=role, content=content
        )


@database_sync_to_async
def conversation_request(conversation_id: str, question: str) -> ChatRequestPayload:
    """Build the agent request from what is already persisted."""
    conversation = Conversation.objects.select_related("ticket").get(
        id=conversation_id
    )
    history = [
        ChatTurn(role="assistant" if m.role == MessageRole.ASSISTANT else "user",
                 content=m.content)
        for m in conversation.messages.order_by("created_at")
    ]

    ticket = conversation.ticket
    chat_ticket = (
        ChatTicket(
            ticket_id=str(ticket.id),
            title=ticket.title,
            description=ticket.description,
        )
        if ticket is not None
        else None
    )
    return ChatRequestPayload(
        conversation_id=conversation_id,
        question=question,
        history=history,
        ticket=chat_ticket,
    )


async def ask(conversation_id: str, question: str) -> None:
    """Persist the rep's turn, then stream the assistant's answer back."""
    try:
        message = await _create_user_message(conversation_id, question)
        await broadcast(
            conversation_group(conversation_id),
            ChatMessageMessage(
                payload=ChatMessagePayload(
                    id=str(message.id),
                    role="user",
                    content=question,
                    created_at=message.created_at.isoformat(),
                )
            ),
        )

        request = await conversation_request(conversation_id, question)
        await ConversationChatClient(conversation_id, request).handle()
    except Exception:
        logger.exception("chat.turn_failed", conversation_id=conversation_id)
        await broadcast(
            conversation_group(conversation_id),
            FEChatErrorMessage(
                payload=FEChatErrorPayload(detail="The assistant is unavailable.")
            ),
        )


@database_sync_to_async
def _create_user_message(conversation_id: str, content: str) -> Message:
    return Message.objects.create(
        conversation_id=conversation_id, role=MessageRole.USER, content=content
    )
