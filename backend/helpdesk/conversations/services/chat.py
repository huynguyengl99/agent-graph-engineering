"""Drive the assistant for one conversation turn.

Unlike triage, nothing here is gated: the rep is the only audience, so the
answer is persisted and broadcast as soon as it finishes. A reply only becomes
irreversible when it is handed to a ticket, which goes through the tickets
channel and its approval gate.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

from channels.db import database_sync_to_async
from django.conf import settings
from django.db import transaction

import structlog
from chanx.messages.base import BaseMessage

from helpdesk.accounts.services.preferences import model_overrides
from helpdesk.agent_client.agent.client import AgentClient
from helpdesk.agent_client.agent_hub_conversation_topic.client import (
    AgentHubConversationTopicClient,
)
from helpdesk.agent_client.agent_hub_conversation_topic.messages import (
    ChatCompleteMessage,
    ChatErrorMessage,
    ChatRequestMessage,
    ChatRequestPayload,
    ChatTicket,
    ChatTokenMessage,
    ChatTurn,
    IncomingMessage,
    ToolApprovalMessage,
    ToolApprovalPayload,
    ToolDecisionMessage,
    ToolDecisionPayload,
)
from helpdesk.agent_client.shared.messages import (
    ModelOverrides,
    ReplayRequestMessage,
    ReplayRequestPayload,
)
from helpdesk.conversations.messages import (
    AssistantDoneMessage,
    AssistantDonePayload,
    ChatMessage,
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
from helpdesk.conversations.messages import (
    ToolApprovalMessage as FEToolApprovalMessage,
)
from helpdesk.conversations.messages import (
    ToolApprovalPayload as FEToolApprovalPayload,
)
from helpdesk.conversations.models import (
    Conversation,
    Message,
    MessageRole,
    PendingApproval,
)
from helpdesk.conversations.serializers import serialize_message
from helpdesk.conversations.topics.conversation_topic import ConversationTopic
from helpdesk.core.agent_connection import agent_headers
from helpdesk.core.services.cursors import advance, advance_sync, last_handled

logger = structlog.get_logger(__name__)

_background: set[asyncio.Task[None]] = set()


def spawn(coro: "Coroutine[Any, Any, None]") -> None:
    """Run detached, keeping a strong reference. See triage.spawn."""
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


def conversation_topic(conversation_id: str) -> str:
    return f"conversation:{conversation_id}"


async def broadcast(topic: str, message: BaseMessage) -> None:
    """Publish to a conversation's subscribers, with no consumer to borrow."""
    await ConversationTopic.broadcast(topic, message)


OutgoingPayload = ChatRequestPayload | ToolDecisionPayload


class _ConversationHandle(AgentHubConversationTopicClient):
    """Forwards the topic's events to the relay that opened it."""

    async def dispatch_frame(self, py_object: dict[str, Any]) -> None:
        """The sequence and the agent's topic ride the envelope, not the message."""
        relay: Any = self.connection
        relay.incoming_seq = int(py_object.get("seq") or 0)
        relay.agent_topic = self.topic
        await super().dispatch_frame(py_object)

    async def handle_message(self, message: IncomingMessage) -> None:
        relay: Any = self.connection
        await relay.on_event(message)


class ConversationChatClient(AgentClient):
    """One turn, then disconnect.

    A turn may end parked at a tool gate instead of at an answer, in which case
    the connection closes with the run still checkpointed in the agent. The
    reviewer's decision subscribes again, exactly as triage does.
    """

    def __init__(self, conversation_id: str, request: OutgoingPayload) -> None:
        super().__init__(settings.AGENT_WS_URL, headers=agent_headers())
        self.conversation_id = conversation_id
        self.payload = request
        self.group = conversation_topic(conversation_id)
        self.answer = ""
        # Both set by the handle before it forwards an event.
        self.incoming_seq = 0
        self.agent_topic = ""

    async def send_init_message(self) -> None:
        topic = self.topic(_ConversationHandle, conversation_id=self.conversation_id)
        # Subscribed before the request, or the run's events race it.
        await topic.subscribe()

        # Whatever finished while nobody was subscribed, before the new request.
        await topic.send_message(
            ReplayRequestMessage(
                payload=ReplayRequestPayload(since=await last_handled(topic.topic))
            )
        )

        if isinstance(self.payload, ChatRequestPayload):
            await topic.send_message(ChatRequestMessage(payload=self.payload))
        else:
            await topic.send_message(ToolDecisionMessage(payload=self.payload))

    async def disconnect(self, code: int = 1000, reason: str = "") -> None:
        if getattr(self, "websocket", None) is None:
            return
        await super().disconnect(code, reason)

    async def on_event(self, message: IncomingMessage) -> None:
        match message:
            case ChatTokenMessage(payload=payload):
                await broadcast(
                    self.group,
                    TokenMessage(payload=TokenPayload(delta=payload.delta)),
                )
            case ToolApprovalMessage(payload=payload):
                await self._remember_proposal(payload)
                await broadcast(
                    self.group,
                    FEToolApprovalMessage(
                        payload=FEToolApprovalPayload(
                            tool=payload.tool,
                            description=payload.description,
                            arguments=payload.arguments,
                            arguments_schema=payload.arguments_schema or {},
                            unknown_arguments=payload.unknown_arguments or [],
                        )
                    ),
                )
                # Parked on a person. Nothing is persisted: the proposal is not
                # a turn, and it only becomes one if it runs.
                await self.disconnect()
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
            case _:
                # A heartbeat, or a message type the agent gained and this
                # relay has not been taught yet. Ignored on purpose, and said
                # so, because an unhandled branch that falls off the end reads
                # like an oversight.
                pass

        await advance(self.agent_topic, self.incoming_seq)

    @database_sync_to_async
    def _remember_proposal(self, payload: ToolApprovalPayload) -> None:
        """So a reload finds the card. The run is already durable in the agent;
        this is the only way the browser can ask what is waiting."""
        PendingApproval.objects.update_or_create(
            conversation_id=self.conversation_id,
            defaults={
                "tool": payload.tool,
                "description": payload.description,
                "arguments": payload.arguments,
                "arguments_schema": payload.arguments_schema or {},
                "unknown_arguments": payload.unknown_arguments or [],
            },
        )

    @staticmethod
    @database_sync_to_async
    def forget_proposal(conversation_id: str) -> None:
        PendingApproval.objects.filter(conversation_id=conversation_id).delete()

    async def _persist_answer(self, content: str) -> None:
        message = await self._create_message(
            self.conversation_id, MessageRole.ASSISTANT, content, self.incoming_seq
        )
        await broadcast(
            self.group,
            AssistantDoneMessage(payload=AssistantDonePayload(message=message)),
        )

    @database_sync_to_async
    def _create_message(
        self, conversation_id: str, role: str, content: str, seq: int = 0
    ) -> ChatMessage:
        """Returns the wire shape, not the model: the payload carries the same
        representation the REST endpoint would return for this row.

        The cursor moves in the same transaction as the row. A turn is the one
        replayable event that is not idempotent - a second insert is a duplicate
        the rep can see - so "written" and "handled" have to commit together.
        """
        with transaction.atomic():
            message = Message.objects.create(
                conversation_id=conversation_id, role=role, content=content
            )
            advance_sync(self.agent_topic, seq)
            return serialize_message(message)


@database_sync_to_async
def conversation_request(
    conversation_id: str, question: str, models: dict[str, str] | None = None
) -> ChatRequestPayload:
    """Build the agent request from what is already persisted."""
    conversation = Conversation.objects.select_related("ticket").get(id=conversation_id)
    history = [
        ChatTurn(
            role="assistant" if m.role == MessageRole.ASSISTANT else "user",
            content=m.content,
        )
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
        models=ModelOverrides(**(models or {})),
    )


async def ask(conversation_id: str, question: str, user_id: Any = None) -> None:
    """Persist the rep's turn, then stream the assistant's answer back."""
    try:
        message = await _create_user_message(conversation_id, question)
        await broadcast(
            conversation_topic(conversation_id),
            ChatMessageMessage(payload=ChatMessagePayload(message=message)),
        )

        request = await conversation_request(
            conversation_id, question, await model_overrides(user_id)
        )
        await ConversationChatClient(conversation_id, request).handle()
    except Exception:
        logger.exception("chat.turn_failed", conversation_id=conversation_id)
        await broadcast(
            conversation_topic(conversation_id),
            FEChatErrorMessage(
                payload=FEChatErrorPayload(detail="The assistant is unavailable.")
            ),
        )


@database_sync_to_async
def _create_user_message(conversation_id: str, content: str) -> ChatMessage:
    return serialize_message(
        Message.objects.create(
            conversation_id=conversation_id, role=MessageRole.USER, content=content
        )
    )


async def start_turn(conversation_id: str, question: str, user_id: Any = None) -> None:
    """Run one turn detached: the answer streams over the topic, not the socket."""
    spawn(ask(conversation_id, question, user_id))


async def decide_tool(
    conversation_id: str, approved: bool, arguments: dict[str, Any]
) -> None:
    """Resume a turn parked at the tool gate.

    A fresh connection: the parked graph lives in the agent's checkpointer
    keyed by conversation, not in the socket that proposed the call.
    """
    try:
        # Cleared first: the card is answered whatever the resumed run does, and
        # a row left behind would reappear on the next page load.
        await ConversationChatClient.forget_proposal(conversation_id)
        await ConversationChatClient(
            conversation_id,
            ToolDecisionPayload(
                conversation_id=conversation_id,
                approved=approved,
                arguments=arguments,
            ),
        ).handle()
    except Exception:
        logger.exception("chat.tool_decision_failed", conversation_id=conversation_id)
        await broadcast(
            conversation_topic(conversation_id),
            FEChatErrorMessage(
                payload=FEChatErrorPayload(detail="The assistant is unavailable.")
            ),
        )


async def start_tool_decision(
    conversation_id: str, *, approved: bool, arguments: dict[str, Any]
) -> None:
    """Detached for the same reason a turn is: the answer streams over the topic."""
    spawn(decide_tool(conversation_id, approved, arguments))
