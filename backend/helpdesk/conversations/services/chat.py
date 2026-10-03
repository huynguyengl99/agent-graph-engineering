"""What a run writes down in a conversation.

The same relay the tickets use, with a different sink: there is no customer
here, so nothing is gated and nothing is published - the answer is a message
in the thread.
"""

from typing import Any

from channels.db import database_sync_to_async
from django.db import transaction

import structlog
from chanx.messages.base import BaseMessage

from helpdesk.accounts.services.preferences import model_overrides
from helpdesk.agent_client.agent_hub_support_topic.messages import (
    ModelOverrides,
    RunRequestPayload,
    RunTurn,
    TicketRef,
    ToolDecisionPayload,
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
from helpdesk.conversations.models import Conversation, Message, MessageRole
from helpdesk.conversations.models.pending_approval import PendingApproval
from helpdesk.conversations.serializers import serialize_message
from helpdesk.conversations.topics.conversation_topic import ConversationTopic
from helpdesk.core.services.cursors import advance_sync
from helpdesk.core.services.support_run import Sink, SupportRun, spawn

logger = structlog.get_logger(__name__)

TEAM = "team"


def conversation_topic(conversation_id: str) -> str:
    return f"conversation:{conversation_id}"


async def broadcast(topic: str, message: BaseMessage) -> None:
    await ConversationTopic.broadcast(topic, message)


class ConversationSink(Sink):
    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.group = conversation_topic(conversation_id)
        self.seq = 0
        self.agent_topic = ""
        self.answer = ""

    async def token(self, delta: str) -> None:
        await broadcast(self.group, TokenMessage(payload=TokenPayload(delta=delta)))

    async def answered(self, content: str) -> None:
        self.answer = content
        message = await self._create_message(MessageRole.ASSISTANT, content)
        await broadcast(
            self.group,
            AssistantDoneMessage(payload=AssistantDonePayload(message=message)),
        )

    async def tool_proposed(self, payload: Any) -> None:
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

    async def failed(self, message: str) -> None:
        await broadcast(
            self.group, FEChatErrorMessage(payload=FEChatErrorPayload(detail=message))
        )

    @database_sync_to_async
    def _remember_proposal(self, payload: Any) -> None:
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

    @database_sync_to_async
    def _create_message(self, role: str, content: str) -> ChatMessage:
        """Returns the wire shape, not the model: the payload carries the same
        representation the REST endpoint would return for this row.

        The cursor moves in the same transaction as the row. A turn is the one
        replayable event that is not idempotent - a second insert is a duplicate
        the rep can see - so "written" and "handled" have to commit together.
        """
        with transaction.atomic():
            message = Message.objects.create(
                conversation_id=self.conversation_id, role=role, content=content
            )
            advance_sync(self.agent_topic, self.seq)
            return serialize_message(message)


class _Run(SupportRun):
    """Keeps the sink's view of the cursor in step with the connection's."""

    async def on_event(self, message: Any) -> None:
        sink: Any = self.sink
        sink.seq, sink.agent_topic = self.incoming_seq, self.agent_topic
        await super().on_event(message)


def relay(conversation_id: str, request: Any = None) -> "_Run":
    """One turn's relay. The request defaults to a fresh run; a resume passes
    its own."""
    return _Run(
        TEAM,
        conversation_id,
        request or RunRequestPayload(),
        ConversationSink(conversation_id),
    )


@database_sync_to_async
def forget_proposal(conversation_id: str) -> None:
    PendingApproval.objects.filter(conversation_id=conversation_id).delete()


@database_sync_to_async
def conversation_request(
    conversation_id: str, question: str, models: dict[str, str] | None = None
) -> RunRequestPayload:
    """Build the agent request from what is already persisted."""
    conversation = Conversation.objects.select_related("ticket").get(id=conversation_id)
    history = [
        RunTurn(
            role="assistant" if m.role == MessageRole.ASSISTANT else "user",
            content=m.content,
        )
        for m in conversation.messages.order_by("created_at")
    ]

    ticket = conversation.ticket
    return RunRequestPayload(
        question=question,
        history=history,
        ticket=(
            TicketRef(
                ticket_id=str(ticket.id),
                title=ticket.title,
                description=ticket.description,
            )
            if ticket is not None
            else None
        ),
        models=ModelOverrides(**(models or {})),
    )


@database_sync_to_async
def _create_user_message(conversation_id: str, content: str) -> ChatMessage:
    return serialize_message(
        Message.objects.create(
            conversation_id=conversation_id, role=MessageRole.USER, content=content
        )
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
        await _Run(
            TEAM, conversation_id, request, ConversationSink(conversation_id)
        ).handle()
    except Exception:
        logger.exception("chat.turn_failed", conversation_id=conversation_id)
        await broadcast(
            conversation_topic(conversation_id),
            FEChatErrorMessage(
                payload=FEChatErrorPayload(detail="The assistant is unavailable.")
            ),
        )


async def start_turn(conversation_id: str, question: str, user_id: Any = None) -> None:
    """Run one turn detached: the answer streams over the topic, not the socket."""
    spawn(ask(conversation_id, question, user_id))


async def decide_tool(
    conversation_id: str, approved: bool, arguments: dict[str, Any]
) -> None:
    """Resume a turn parked at the tool gate.

    A fresh connection: the parked graph lives in the agent's checkpointer keyed
    by the thread, not in the socket that proposed the call.
    """
    try:
        # Cleared first: the card is answered whatever the resumed run does, and
        # a row left behind would reappear on the next page load.
        await forget_proposal(conversation_id)
        await _Run(
            TEAM,
            conversation_id,
            ToolDecisionPayload(
                conversation_id=conversation_id,
                approved=approved,
                arguments=arguments,
            ),
            ConversationSink(conversation_id),
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
