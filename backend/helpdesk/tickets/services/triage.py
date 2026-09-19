"""Drive the agent's triage graph for one ticket.

The backend holds no socket of its own here. It opens a short-lived client to
the agent, feeds it the ticket, and fans every result into the ticket's channel
group, so any browser tab on that ticket sees the run regardless of which one
posted the comment.
"""

import logging
from typing import Any

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings

from chanx.messages.base import BaseMessage

from helpdesk.agent_client.triage.client import TriageClient
from helpdesk.agent_client.triage.messages import (
    AnswerMessage,
    ApprovalDecisionMessage,
    ApprovalDecisionPayload,
    ApprovalRequiredMessage,
    ClassifiedMessage,
    DecidedMessage,
    IncomingMessage,
    ReplySentMessage,
    TriageErrorMessage,
    TriageRequestMessage,
    TriageRequestPayload,
)
from helpdesk.tickets.messages import (
    AgentProgressMessage,
    AgentProgressPayload,
    NewEventMessage,
    NewEventPayload,
)
from helpdesk.tickets.messages import (
    ApprovalRequiredMessage as FEApprovalRequiredMessage,
)
from helpdesk.tickets.messages import (
    ApprovalRequiredPayload as FEApprovalRequiredPayload,
)
from helpdesk.tickets.models import AIResponseEvent
from helpdesk.tickets.serializers.event import serialize_event

logger = logging.getLogger(__name__)

OutgoingPayload = TriageRequestPayload | ApprovalDecisionPayload


def ticket_group(ticket_id: str) -> str:
    return f"ticket_{ticket_id}"


async def broadcast(group: str, message: BaseMessage) -> None:
    """Send a chanx message to a group without owning a consumer.

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


class TicketTriageClient(TriageClient):
    """Runs one triage request, then disconnects."""

    def __init__(self, ticket_id: str, request: OutgoingPayload) -> None:
        super().__init__(settings.AGENT_WS_URL)
        self.ticket_id = ticket_id
        self.request = request
        self.group = ticket_group(ticket_id)
        self.pending_reply: str | None = None

    async def send_init_message(self) -> None:
        if isinstance(self.request, TriageRequestPayload):
            await self.send_message(TriageRequestMessage(payload=self.request))
        else:
            await self.send_message(ApprovalDecisionMessage(payload=self.request))

    async def disconnect(self, code: int = 1000, reason: str = "") -> None:
        """Closing a run that never opened a socket is not an error.

        The terminal handlers below call this unconditionally, and the agent
        may also have dropped the connection first.
        """
        if getattr(self, "websocket", None) is None:
            return
        await super().disconnect(code, reason)

    async def handle_message(self, message: IncomingMessage) -> None:
        match message:
            case ClassifiedMessage(payload=payload):
                await broadcast(
                    self.group,
                    AgentProgressMessage(
                        payload=AgentProgressPayload(
                            stage="classified",
                            detail=(
                                f"{payload.category} / {payload.priority}: "
                                f"{payload.reasoning}"
                            ),
                        )
                    ),
                )
            case DecidedMessage(payload=payload):
                await broadcast(
                    self.group,
                    AgentProgressMessage(
                        payload=AgentProgressPayload(
                            stage="decided",
                            detail=f"{payload.decision}: {payload.reasoning}",
                        )
                    ),
                )
            case ApprovalRequiredMessage(payload=payload):
                await broadcast(
                    self.group,
                    FEApprovalRequiredMessage(
                        payload=FEApprovalRequiredPayload(draft=payload.draft)
                    ),
                )
                # The run is parked in the agent's checkpointer. Release the
                # socket; the reviewer's decision opens a fresh one.
                await self.disconnect()

            case ReplySentMessage():
                # The reply actually went out, so it becomes a ticket event.
                event = await self._persist_answer(self.pending_reply or "")
                await broadcast(
                    self.group,
                    NewEventMessage(payload=NewEventPayload(event=event)),
                )
                await self.disconnect()

            case AnswerMessage(payload=payload):
                # Remember the draft; it is persisted only if it is sent.
                self.pending_reply = payload.content
                if not payload.requires_approval:
                    event = await self._persist_answer(payload.content)
                    await broadcast(
                        self.group,
                        NewEventMessage(payload=NewEventPayload(event=event)),
                    )
                    await self.disconnect()
            case TriageErrorMessage(payload=payload):
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

    @database_sync_to_async
    def _persist_answer(self, content: str) -> dict[str, Any]:
        event = AIResponseEvent.objects.create(
            ticket_id=self.ticket_id,
            content=content,
            model_name=settings.AGENT_ANSWER_MODEL,
        )
        return serialize_event(event)


async def run_triage(
    ticket_id: str, title: str, description: str, history: list[str]
) -> None:
    """Best-effort triage. A failure must never take down the chat socket.

    Everything runs inside the guard, including building the request: this is a
    detached task, so an escaping exception would surface only as an unretrieved
    future and the user would see the UI hang with no explanation.
    """
    try:
        client = TicketTriageClient(
            ticket_id,
            TriageRequestPayload(
                ticket_id=ticket_id,
                title=title,
                description=description,
                history=history,
            ),
        )
        await client.handle()
    except Exception:
        logger.exception("Triage run failed for ticket %s", ticket_id)
        await broadcast(
            ticket_group(ticket_id),
            AgentProgressMessage(
                payload=AgentProgressPayload(
                    stage="failed", detail="The triage agent is unavailable."
                )
            ),
        )


async def submit_approval(
    ticket_id: str, approved: bool, content: str | None = None
) -> None:
    """Resume a run parked at the approval gate.

    A separate connection from the one that started the run: the graph lives in
    the agent's checkpointer keyed by ticket, not in the socket.
    """
    try:
        client = TicketTriageClient(
            ticket_id,
            ApprovalDecisionPayload(
                ticket_id=ticket_id, approved=approved, content=content
            ),
        )
        client.pending_reply = content
        await client.handle()
    except Exception:
        logger.exception("Approval submit failed for ticket %s", ticket_id)
        await broadcast(
            ticket_group(ticket_id),
            AgentProgressMessage(
                payload=AgentProgressPayload(
                    stage="failed", detail="Could not reach the triage agent."
                )
            ),
        )
