"""Drive the agent's triage graph for one ticket.

The backend holds no socket of its own here. It opens a short-lived client to
the agent, feeds it the ticket, and fans every result into the ticket's channel
group, so any browser tab on that ticket sees the run regardless of which one
posted the comment.
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
from helpdesk.agent_client.agent_hub_triage_topic.client import (
    AgentHubTriageTopicClient,
)
from helpdesk.agent_client.agent_hub_triage_topic.messages import (
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
)
from helpdesk.tickets.messages import (
    ApprovalRequiredMessage as FEApprovalRequiredMessage,
)
from helpdesk.tickets.messages import (
    ApprovalRequiredPayload as FEApprovalRequiredPayload,
)
from helpdesk.tickets.messages.events import TicketEvent as WireTicketEvent
from helpdesk.tickets.models import AIResponseEvent, Handling, PendingReply, Visibility
from helpdesk.tickets.serializers.event import serialize_event
from helpdesk.tickets.services.handoff import hand_off
from helpdesk.tickets.topics.ticket_topic import TicketTopic

logger = structlog.get_logger(__name__)

_background: set[asyncio.Task[None]] = set()


def spawn(coro: "Coroutine[Any, Any, None]") -> None:
    """Run detached, keeping a strong reference.

    asyncio holds only a weak reference to a running task, so a detached one
    can be collected mid-flight. The discard callback stops the set growing.
    """
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


OutgoingPayload = TriageRequestPayload | ApprovalDecisionPayload


def ticket_topic(ticket_id: str) -> str:
    return f"ticket:{ticket_id}"


async def broadcast(topic: str, message: BaseMessage) -> None:
    """Publish to a ticket's subscribers.

    `Topic.broadcast` is a classmethod, which is the whole point: this runs in
    a detached task driving a client to the agent, with no consumer instance to
    borrow.
    """
    await TicketTopic.broadcast(topic, message)


class _TriageHandle(AgentHubTriageTopicClient):
    """Forwards the topic's events to the relay that opened it."""

    async def dispatch_frame(self, py_object: dict[str, Any]) -> None:
        """The sequence and the agent's topic ride the envelope, not the message.

        The topic comes from the handle because `self.group` is a different
        string: this service fans out to `ticket:<id>`, the agent files under
        `triage:<id>`.
        """
        relay: Any = self.connection
        relay.incoming_seq = int(py_object.get("seq") or 0)
        relay.agent_topic = self.topic
        await super().dispatch_frame(py_object)

    async def handle_message(self, message: IncomingMessage) -> None:
        relay: Any = self.connection
        await relay.on_event(message)


class TicketTriageClient(AgentClient):
    """Runs one triage request, then disconnects.

    One connection with a subscription per ticket, rather than a socket per
    channel: the run belongs to `triage:<ticket_id>`, so a resume arrives on a
    subscription that is already open and a node can emit to it directly.
    """

    def __init__(
        self,
        ticket_id: str,
        request: OutgoingPayload,
        visibility: str = Visibility.PUBLIC,
    ) -> None:
        super().__init__(settings.AGENT_WS_URL, headers=agent_headers())
        self.ticket_id = ticket_id
        self.payload = request
        self.visibility = visibility
        self.group = ticket_topic(ticket_id)
        # Both set by the handle before it forwards an event.
        self.incoming_seq = 0
        self.agent_topic = ""
        self.pending_reply: str | None = None

    async def send_init_message(self) -> None:
        topic = self.topic(_TriageHandle, ticket_id=self.ticket_id)
        # Subscribed before the request, or the run's own events race the
        # subscription and the first ones are dropped.
        await topic.subscribe()

        # Whatever finished while nobody was subscribed, before the new request.
        await topic.send_message(
            ReplayRequestMessage(
                payload=ReplayRequestPayload(since=await last_handled(topic.topic))
            )
        )

        if isinstance(self.payload, TriageRequestPayload):
            await topic.send_message(TriageRequestMessage(payload=self.payload))
        else:
            await topic.send_message(ApprovalDecisionMessage(payload=self.payload))

    async def disconnect(self, code: int = 1000, reason: str = "") -> None:
        """Closing a run that never opened a socket is not an error.

        The terminal handlers below call this unconditionally, and the agent
        may also have dropped the connection first.
        """
        if getattr(self, "websocket", None) is None:
            return
        await super().disconnect(code, reason)

    async def on_event(self, message: IncomingMessage) -> None:
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
                if payload.decision == "Escalate":
                    await self._hand_to_a_person(payload.reasoning)
            case ApprovalRequiredMessage(payload=payload):
                await self._remember_draft(payload.draft, payload.findings)
                await broadcast(
                    self.group,
                    FEApprovalRequiredMessage(
                        payload=FEApprovalRequiredPayload(
                            draft=payload.draft, findings=payload.findings
                        )
                    ),
                )
                # The run is parked in the agent's checkpointer. Release the
                # socket; the reviewer's decision opens a fresh one.
                await self.disconnect()

            case ReplySentMessage():
                # The reply actually went out, so it becomes a ticket event.
                event = await self._persist_answer(await self._sent_text())
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

        await advance(self.agent_topic, self.incoming_seq)

    async def _hand_to_a_person(self, reason: str) -> None:
        event = await hand_off(self.ticket_id, Handling.NEEDS_HUMAN, reason=reason)
        if event is not None:
            await broadcast(
                self.group, NewEventMessage(payload=NewEventPayload(event=event))
            )

    @database_sync_to_async
    def _remember_draft(self, draft: str, findings: list[str]) -> None:
        PendingReply.objects.update_or_create(
            ticket_id=self.ticket_id,
            defaults={
                "draft": draft,
                "findings": findings,
                "visibility": self.visibility,
            },
        )

    async def _sent_text(self) -> str:
        """The reviewer's edit if they made one, otherwise the stored draft.

        `reply_sent` carries a receipt and not the text, so before the draft was
        persisted a plain approve recorded an empty event on the ticket.
        """
        if self.pending_reply:
            return self.pending_reply
        return str(await self._stored_draft(self.ticket_id))

    @staticmethod
    @database_sync_to_async
    def _stored_draft(ticket_id: str) -> str:
        pending = PendingReply.objects.filter(ticket_id=ticket_id).first()
        return str(pending.draft) if pending else ""

    @staticmethod
    @database_sync_to_async
    def forget_draft(ticket_id: str) -> None:
        PendingReply.objects.filter(ticket_id=ticket_id).delete()

    @database_sync_to_async
    def _persist_answer(self, content: str) -> WireTicketEvent:
        """A sent reply is the one replayable event that is not idempotent, so the
        cursor commits with the row."""
        with transaction.atomic():
            event = AIResponseEvent.objects.create(
                ticket_id=self.ticket_id,
                content=content,
                model_name=settings.AGENT_ANSWER_MODEL,
                visibility=self.visibility,
            )
            advance_sync(self.agent_topic, self.incoming_seq)
            return serialize_event(event)


async def run_triage(
    ticket_id: str,
    title: str,
    description: str,
    history: list[str],
    models: dict[str, str] | None = None,
    visibility: str = Visibility.PUBLIC,
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
                models=ModelOverrides(**(models or {})),
            ),
            visibility=visibility,
        )
        await client.handle()
    except Exception:
        logger.exception("triage.run_failed", ticket_id=ticket_id)
        await broadcast(
            ticket_topic(ticket_id),
            AgentProgressMessage(
                payload=AgentProgressPayload(
                    stage="failed", detail="The triage agent is unavailable."
                )
            ),
        )


@database_sync_to_async
def _parked_visibility(ticket_id: str) -> str:
    pending = PendingReply.objects.filter(ticket_id=ticket_id).first()
    return str(pending.visibility) if pending else Visibility.PUBLIC


async def submit_approval(
    ticket_id: str,
    approved: bool,
    content: str | None = None,
    models: dict[str, str] | None = None,
) -> None:
    """Resume a run parked at the approval gate.

    A separate connection from the one that started the run: the graph lives in
    the agent's checkpointer keyed by ticket, not in the socket.
    """
    try:
        client = TicketTriageClient(
            ticket_id,
            ApprovalDecisionPayload(
                ticket_id=ticket_id,
                approved=approved,
                content=content,
                models=ModelOverrides(**(models or {})),
            ),
            visibility=await _parked_visibility(ticket_id),
        )
        client.pending_reply = content
        await client.handle()
        # Decided either way, so the card is answered. Done after the run so a
        # failure to reach the agent leaves it recoverable.
        await TicketTriageClient.forget_draft(ticket_id)
    except Exception:
        logger.exception("triage.approval_failed", ticket_id=ticket_id)
        await broadcast(
            ticket_topic(ticket_id),
            AgentProgressMessage(
                payload=AgentProgressPayload(
                    stage="failed", detail="Could not reach the triage agent."
                )
            ),
        )


@database_sync_to_async
def _ticket_context(ticket_id: str) -> dict[str, Any]:
    from helpdesk.tickets.models import CommentEvent, Ticket

    ticket = Ticket.objects.get(id=ticket_id)
    # Internal notes go too: a staff note is often the reason a reply should say
    # something different. Labelled, because the agent must not quote one back.
    comments = CommentEvent.objects.filter(ticket_id=ticket_id).order_by("created_at")
    history = [
        c.content
        if c.visibility == Visibility.PUBLIC
        else f"[internal note, not for the customer] {c.content}"
        for c in comments
    ]
    return {
        "title": ticket.title,
        "description": ticket.description,
        "history": history,
    }


async def start_triage(
    ticket_id: str, user_id: Any = None, visibility: str = Visibility.PUBLIC
) -> None:
    """Kick off triage without holding the socket.

    Detached because the agent may take tens of seconds; results reach the
    browser through the ticket topic, not this return path.
    """
    context = await _ticket_context(ticket_id)
    spawn(
        run_triage(
            ticket_id=ticket_id,
            title=context["title"],
            description=context["description"],
            history=context["history"],
            models=await model_overrides(user_id),
            visibility=visibility,
        )
    )


async def start_approval(
    ticket_id: str,
    *,
    approved: bool,
    content: str | None = None,
    user_id: Any = None,
) -> None:
    """Resume a parked run. Detached for the same reason."""
    spawn(
        submit_approval(
            ticket_id=ticket_id,
            approved=approved,
            content=content,
            models=await model_overrides(user_id),
        )
    )
