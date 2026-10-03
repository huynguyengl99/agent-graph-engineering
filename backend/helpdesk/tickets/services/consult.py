"""The agent as a colleague on the ticket's internal lane.

Triage answers the customer. This answers whoever is working the ticket, so it
drives the chat graph instead, keyed by the ticket: the agent keeps the thread,
and what comes back is an internal event.
"""

from typing import Any

from channels.db import database_sync_to_async
from django.conf import settings
from django.db import transaction

import structlog

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
from helpdesk.core.agent_connection import agent_headers
from helpdesk.core.services.cursors import advance, advance_sync, last_handled
from helpdesk.tickets.messages import (
    AgentProgressMessage,
    AgentProgressPayload,
    NewEventMessage,
    NewEventPayload,
    ToolProposalMessage,
    ToolProposalPayload,
)
from helpdesk.tickets.models import (
    AIResponseEvent,
    CommentEvent,
    PendingToolCall,
    Ticket,
    Visibility,
)
from helpdesk.tickets.serializers.event import serialize_event
from helpdesk.tickets.services.placeholders import refuse_if_unfilled
from helpdesk.tickets.services.triage import broadcast, spawn, ticket_topic

logger = structlog.get_logger(__name__)


class _ConsultHandle(AgentHubConversationTopicClient):
    async def dispatch_frame(self, py_object: dict[str, Any]) -> None:
        relay: Any = self.connection
        relay.incoming_seq = int(py_object.get("seq") or 0)
        relay.agent_topic = self.topic
        await super().dispatch_frame(py_object)

    async def handle_message(self, message: IncomingMessage) -> None:
        relay: Any = self.connection
        await relay.on_event(message)


class TicketConsultClient(AgentClient):
    """One internal question, answered on the ticket."""

    def __init__(
        self,
        ticket_id: str,
        request: ChatRequestPayload | ToolDecisionPayload,
        visibility: str = Visibility.INTERNAL,
    ) -> None:
        super().__init__(settings.AGENT_WS_URL, headers=agent_headers())
        self.ticket_id = ticket_id
        self.payload = request
        self.visibility = visibility
        self.group = ticket_topic(ticket_id)
        self.incoming_seq = 0
        self.agent_topic = ""

    async def send_init_message(self) -> None:
        topic = self.topic(_ConsultHandle, conversation_id=self.ticket_id)
        await topic.subscribe()
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
            case ChatCompleteMessage(payload=payload):
                event = await self._persist(payload.content)
                await broadcast(
                    self.group, NewEventMessage(payload=NewEventPayload(event=event))
                )
                await self.disconnect()
            case ToolApprovalMessage(payload=payload):
                await self._remember_proposal(payload)
                await broadcast(
                    self.group,
                    ToolProposalMessage(
                        payload=ToolProposalPayload(
                            tool=payload.tool,
                            description=payload.description,
                            arguments=payload.arguments,
                            arguments_schema=payload.arguments_schema or {},
                            unknown_arguments=payload.unknown_arguments or [],
                        )
                    ),
                )
                # Parked on a person. Nothing is persisted: a proposal is not
                # an answer, and it only becomes one if it runs.
                await self.disconnect()
            case ChatErrorMessage(payload=payload):
                await broadcast(
                    self.group,
                    AgentProgressMessage(
                        payload=AgentProgressPayload(
                            stage="failed", detail=payload.message
                        )
                    ),
                )
                await self.disconnect()
            case _:
                pass

        await advance(self.agent_topic, self.incoming_seq)

    @database_sync_to_async
    def _remember_proposal(self, payload: ToolApprovalPayload) -> None:
        PendingToolCall.objects.update_or_create(
            ticket_id=self.ticket_id,
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
    def forget_proposal(ticket_id: str) -> None:
        PendingToolCall.objects.filter(ticket_id=ticket_id).delete()

    @database_sync_to_async
    def _persist(self, content: str) -> Any:
        if self.visibility == Visibility.PUBLIC:
            refuse_if_unfilled(content)
        with transaction.atomic():
            event = AIResponseEvent.objects.create(
                ticket_id=self.ticket_id,
                content=content,
                model_name=settings.AGENT_ANSWER_MODEL,
                visibility=self.visibility,
            )
            advance_sync(self.agent_topic, self.incoming_seq)
            return serialize_event(event)


@database_sync_to_async
def _consult_request(
    ticket_id: str, question: str, models: dict[str, str] | None
) -> ChatRequestPayload:
    ticket = Ticket.objects.get(id=ticket_id)
    history = [
        ChatTurn(
            role="assistant" if isinstance(event, AIResponseEvent) else "user",
            content=event.content,
        )
        for event in ticket.events.instance_of(CommentEvent, AIResponseEvent).order_by(
            "created_at"
        )
    ]
    return ChatRequestPayload(
        conversation_id=ticket_id,
        question=question,
        history=history,
        ticket=ChatTicket(
            ticket_id=ticket_id,
            title=ticket.title,
            description=ticket.description,
        ),
        models=ModelOverrides(**(models or {})),
    )


async def consult(ticket_id: str, question: str, user_id: Any = None) -> None:
    try:
        request = await _consult_request(
            ticket_id, question, await model_overrides(user_id)
        )
        await TicketConsultClient(ticket_id, request).handle()
    except Exception:
        logger.exception("consult.failed", ticket_id=ticket_id)
        await broadcast(
            ticket_topic(ticket_id),
            AgentProgressMessage(
                payload=AgentProgressPayload(
                    stage="failed", detail="The agent could not answer that."
                )
            ),
        )


async def start_consult(ticket_id: str, question: str, user_id: Any = None) -> None:
    spawn(consult(ticket_id, question, user_id))


async def decide_tool(
    ticket_id: str, *, approved: bool, arguments: dict[str, Any], publish: bool
) -> None:
    """Resume a consult parked at the tool gate.

    What the agent writes afterwards goes where the reviewer said: a refund they
    approved is the customer's news, a lookup they ran is the team's.
    """
    try:
        # Cleared first: the card is answered whatever the resumed run does.
        await TicketConsultClient.forget_proposal(ticket_id)
        await TicketConsultClient(
            ticket_id,
            ToolDecisionPayload(
                conversation_id=ticket_id, approved=approved, arguments=arguments
            ),
            visibility=Visibility.PUBLIC if publish else Visibility.INTERNAL,
        ).handle()
    except Exception:
        logger.exception("consult.tool_decision_failed", ticket_id=ticket_id)
        await broadcast(
            ticket_topic(ticket_id),
            AgentProgressMessage(
                payload=AgentProgressPayload(
                    stage="failed", detail="That tool call could not be finished."
                )
            ),
        )


async def start_tool_decision(
    ticket_id: str, *, approved: bool, arguments: dict[str, Any], publish: bool
) -> None:
    spawn(
        decide_tool(ticket_id, approved=approved, arguments=arguments, publish=publish)
    )
