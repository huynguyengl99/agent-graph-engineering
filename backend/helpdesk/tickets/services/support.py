"""What a run writes down on a ticket.

One sink for both audiences: a customer's run drafts a reply behind the
approval gate, the team's answers the lane they asked in, and the visibility
the answer is filed under is the difference.
"""

from typing import Any, Literal

from channels.db import database_sync_to_async
from django.conf import settings
from django.db import transaction

import structlog
from chanx.messages.base import BaseMessage

from helpdesk.accounts.services.preferences import model_overrides
from helpdesk.agent_client.agent_hub_support_topic.messages import (
    ApprovalDecisionPayload,
    ModelOverrides,
    RunRequestPayload,
    RunTurn,
    TicketRef,
    ToolDecisionPayload,
)
from helpdesk.core.services.cursors import advance_sync
from helpdesk.core.services.support_run import Sink, SupportRun, spawn
from helpdesk.tickets.messages import (
    AgentProgressMessage,
    AgentProgressPayload,
    ApprovalRequiredMessage,
    ApprovalRequiredPayload,
    NewEventMessage,
    NewEventPayload,
    ReasoningDeltaMessage,
    ReasoningDeltaPayload,
    ToolProposalMessage,
    ToolProposalPayload,
)
from helpdesk.tickets.models import (
    AIResponseEvent,
    CommentEvent,
    Handling,
    PendingReply,
    PendingToolCall,
    ReasoningEvent,
    Ticket,
    ToolCallEvent,
    Visibility,
)
from helpdesk.tickets.serializers.event import serialize_event
from helpdesk.tickets.services import lanes
from helpdesk.tickets.services.handoff import hand_off
from helpdesk.tickets.services.placeholders import UnfilledError, refuse_if_unfilled
from helpdesk.tickets.services.status import set_priority, ticket_state
from helpdesk.tickets.topics.ticket_topic import TicketTopic

logger = structlog.get_logger(__name__)

CUSTOMER = "customer"
TEAM = "team"


def ticket_topic(ticket_id: str) -> str:
    return f"ticket:{ticket_id}"


async def broadcast(topic: str, message: BaseMessage) -> None:
    """Publish to a ticket's subscribers.

    `Topic.broadcast` is a classmethod, which is the whole point: this runs in a
    detached task driving a client to the agent, with no consumer instance to
    borrow.
    """
    await TicketTopic.broadcast(topic, message)


class TicketSink(Sink):
    def __init__(self, ticket_id: str, visibility: str) -> None:
        self.ticket_id = ticket_id
        self.visibility = visibility
        self.group = ticket_topic(ticket_id)
        self.seq = 0
        self.agent_topic = ""
        self.draft: str | None = None

    async def _progress(
        self, stage: Literal["classified", "decided", "failed"], detail: str
    ) -> None:
        await broadcast(
            self.group,
            AgentProgressMessage(
                payload=AgentProgressPayload(stage=stage, detail=detail)
            ),
        )

    async def _event(self, event: Any) -> None:
        if event is not None:
            await broadcast(
                self.group, NewEventMessage(payload=NewEventPayload(event=event))
            )

    async def classified(self, category: str, priority: str, why: str) -> None:
        if await set_priority(self.ticket_id, priority):
            await broadcast(self.group, await ticket_state(self.ticket_id))
        await self._progress("classified", f"{category} / {priority}: {why}")

    async def decided(self, decision: str, why: str) -> None:
        await self._progress("decided", f"{decision}: {why}")
        if decision == "Escalate":
            await self._to_a_person(why)

    async def drafted(self, content: str, requires_approval: bool) -> None:
        # Remembered, not persisted: a draft becomes an event only if it is sent.
        self.draft = content
        if not requires_approval:
            await self._event(await self._persist(content))

    async def approval_required(self, draft: str, findings: list[str]) -> None:
        await self._remember_draft(draft, findings)
        await broadcast(
            self.group,
            ApprovalRequiredMessage(
                payload=ApprovalRequiredPayload(draft=draft, findings=findings)
            ),
        )

    async def reply_sent(self) -> None:
        await self._event(await self._persist(await self._sent_text()))

    async def reply_blocked(self, findings: list[str]) -> None:
        await self._progress("failed", "; ".join(findings) or "The reply was blocked.")

    async def answered(self, content: str) -> None:
        await self._event(await self._persist(content))

    async def tool_proposed(self, payload: Any) -> None:
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

    async def tool_ran(self, payload: Any) -> None:
        await self._event(await self._persist_tool_call(payload))

    async def reasoning_delta(self, step: str, delta: str) -> None:
        """Live only. The finished reasoning is the record; the pieces are how
        it looked being written."""
        await broadcast(
            self.group,
            ReasoningDeltaMessage(
                payload=ReasoningDeltaPayload(step=step, delta=delta)
            ),
        )

    async def reasoned(
        self, step: str, content: str, decision: str, model: str
    ) -> None:
        if content:
            await self._event(
                await self._persist_reasoning(step, content, decision, model)
            )

    async def failed(self, message: str) -> None:
        await self._progress("failed", message)
        # The progress line is the team's. Without this the customer waits on a
        # run that is never coming back.
        if self.visibility == Visibility.PUBLIC:
            await self._to_a_person(message)

    async def _to_a_person(self, reason: str) -> None:
        await self._event(
            await hand_off(self.ticket_id, Handling.NEEDS_HUMAN, reason=reason)
        )

    async def _sent_text(self) -> str:
        """The reviewer's edit if they made one, otherwise the stored draft.

        `reply_sent` carries a receipt and not the text, so before the draft was
        persisted a plain approve recorded an empty event on the ticket.
        """
        return self.draft or str(await stored_draft(self.ticket_id))

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

    @database_sync_to_async
    def _remember_proposal(self, payload: Any) -> None:
        PendingToolCall.objects.update_or_create(
            ticket_id=self.ticket_id,
            defaults={
                "tool": payload.tool,
                "description": payload.description,
                "arguments": payload.arguments,
                "arguments_schema": payload.arguments_schema or {},
                "unknown_arguments": payload.unknown_arguments or [],
                "visibility": self.visibility,
            },
        )

    @database_sync_to_async
    def _persist_reasoning(
        self, step: str, content: str, decision: str, model: str
    ) -> Any:
        """Internal whoever started the run: the customer asked a question, not
        for the workings."""
        return serialize_event(
            ReasoningEvent.objects.create(
                ticket_id=self.ticket_id,
                step=step,
                content=content,
                decision=decision,
                model_name=model,
                visibility=Visibility.INTERNAL,
            )
        )

    @database_sync_to_async
    def _persist_tool_call(self, payload: Any) -> Any:
        """Something was done about their ticket, so a customer's run says so.

        What it was given and what came back stays with the team: the serializer
        and the relay strip both for anyone else. A lookup the team ran on their
        own is not the customer's business at all.
        """
        return serialize_event(
            ToolCallEvent.objects.create(
                ticket_id=self.ticket_id,
                tool=payload.tool,
                arguments=payload.arguments,
                result=payload.result,
                error=payload.error,
                cancelled=payload.cancelled,
                visibility=self.visibility,
            )
        )

    @database_sync_to_async
    def _persist(self, content: str) -> Any:
        """A sent reply is the one replayable event that is not idempotent, so
        the cursor commits with the row."""
        if self.visibility == Visibility.PUBLIC:
            refuse_if_unfilled(content)
        with transaction.atomic():
            event = AIResponseEvent.objects.create(
                ticket_id=self.ticket_id,
                content=content,
                model_name=settings.AGENT_ANSWER_MODEL,
                visibility=self.visibility,
            )
            advance_sync(self.agent_topic, self.seq)
            return serialize_event(event)


class _Run(SupportRun):
    """Keeps the sink's view of the cursor in step with the connection's."""

    async def on_event(self, message: Any) -> None:
        sink: Any = self.sink
        sink.seq, sink.agent_topic = self.incoming_seq, self.agent_topic
        await super().on_event(message)


@database_sync_to_async
def stored_draft(ticket_id: str) -> str:
    pending = PendingReply.objects.filter(ticket_id=ticket_id).first()
    return str(pending.draft) if pending else ""


@database_sync_to_async
def parked_visibility(ticket_id: str) -> str:
    pending = PendingReply.objects.filter(ticket_id=ticket_id).first()
    return str(pending.visibility) if pending else Visibility.PUBLIC


@database_sync_to_async
def forget_draft(ticket_id: str) -> None:
    PendingReply.objects.filter(ticket_id=ticket_id).delete()


@database_sync_to_async
def parked_tool_lane(ticket_id: str) -> str:
    """The lane of the run holding the gate, which is not where the reviewer
    chose to send the answer."""
    parked = PendingToolCall.objects.filter(ticket_id=ticket_id).first()
    return str(parked.visibility) if parked else Visibility.INTERNAL


@database_sync_to_async
def forget_proposal(ticket_id: str) -> None:
    PendingToolCall.objects.filter(ticket_id=ticket_id).delete()


@database_sync_to_async
def _request(ticket_id: str, question: str, models: dict[str, str] | None) -> Any:
    """What the agent is told, built from what is already persisted."""
    ticket = Ticket.objects.get(id=ticket_id)
    events = ticket.events.instance_of(CommentEvent, AIResponseEvent).order_by(
        "created_at"
    )
    history = [
        RunTurn(
            role="assistant" if isinstance(event, AIResponseEvent) else "user",
            content=(
                event.content
                if event.visibility == Visibility.PUBLIC
                else f"[internal note, not for the customer] {event.content}"
            ),
        )
        for event in events
    ]
    return RunRequestPayload(
        question=question,
        ticket=TicketRef(
            ticket_id=ticket_id, title=ticket.title, description=ticket.description
        ),
        history=history,
        models=ModelOverrides(**(models or {})),
    )


def relay(
    ticket_id: str, visibility: str = Visibility.PUBLIC, request: Any = None
) -> "_Run":
    """One run's relay. Built here so a caller - or a test - does not have to
    know which audience goes with which visibility."""
    audience = CUSTOMER if visibility == Visibility.PUBLIC else TEAM
    return _Run(
        audience,
        ticket_id,
        request or RunRequestPayload(),
        TicketSink(ticket_id, visibility),
    )


async def run(
    ticket_id: str, *, question: str = "", visibility: str, user_id: Any = None
) -> None:
    """One run on a ticket, then whatever arrived while it was working.

    A failure must never take down the socket that asked, so everything is
    inside the guard, including building the request: this is a detached task,
    so an escaping exception would surface only as an unretrieved future and
    the person would see the UI hang with no explanation.
    """
    if not await lanes.claim(ticket_id, visibility, question, user_id):
        # Another run holds this lane. It will pick this up when it lets go.
        return

    audience = CUSTOMER if visibility == Visibility.PUBLIC else TEAM
    while True:
        try:
            request = await _request(
                ticket_id, question, await model_overrides(user_id)
            )
            await _Run(
                audience, ticket_id, request, TicketSink(ticket_id, visibility)
            ).handle()
        except Exception:
            logger.exception("support.run_failed", ticket_id=ticket_id)
            await broadcast(
                ticket_topic(ticket_id),
                AgentProgressMessage(
                    payload=AgentProgressPayload(
                        stage="failed", detail="The agent is unavailable."
                    )
                ),
            )

        queued = await release(ticket_id, visibility)
        if queued is None:
            return
        question, user_id = queued.question, queued.user_id


async def release(ticket_id: str, visibility: str) -> lanes.Queued | None:
    """Let go of the lane and say what was waiting.

    Its own function so a resumed run - approval or tool gate - releases the
    same way the run that parked it would have.
    """
    queued: lanes.Queued | None = await lanes.release(ticket_id, visibility)
    return queued


async def _then_whatever_waited(ticket_id: str, visibility: str) -> None:
    """A resumed run is the end of the one that parked, so it lets the lane go
    and answers whatever arrived while a person was deciding."""
    queued = await release(ticket_id, visibility)
    if queued is not None:
        await start_run(
            ticket_id,
            question=queued.question,
            visibility=visibility,
            user_id=queued.user_id,
        )


async def start_run(
    ticket_id: str, *, question: str = "", visibility: str, user_id: Any = None
) -> None:
    """Detached: the agent may take tens of seconds, and the results reach the
    browser through the ticket topic rather than this return path."""
    spawn(run(ticket_id, question=question, visibility=visibility, user_id=user_id))


async def submit_approval(
    ticket_id: str,
    approved: bool,
    content: str | None = None,
    models: dict[str, str] | None = None,
) -> None:
    """Resume a run parked at the approval gate.

    A separate connection from the one that started the run: the graph lives in
    the agent's checkpointer keyed by the thread, not in the socket.
    """
    visibility = await parked_visibility(ticket_id)
    if approved and visibility == Visibility.PUBLIC:
        try:
            refuse_if_unfilled(content or await stored_draft(ticket_id))
        except UnfilledError as unfilled:
            await broadcast(
                ticket_topic(ticket_id),
                AgentProgressMessage(
                    payload=AgentProgressPayload(
                        stage="failed",
                        detail=(
                            "Fill in "
                            + ", ".join(unfilled.names)
                            + " before this can go to the customer."
                        ),
                    )
                ),
            )
            return

    sink = TicketSink(ticket_id, visibility)
    sink.draft = content
    try:
        await _Run(
            CUSTOMER,
            ticket_id,
            ApprovalDecisionPayload(
                ticket_id=ticket_id,
                approved=approved,
                content=content,
                models=ModelOverrides(**(models or {})),
            ),
            sink,
        ).handle()
        # Decided either way, so the card is answered. Done after the run so a
        # failure to reach the agent leaves it recoverable.
        await forget_draft(ticket_id)
    except Exception:
        logger.exception("support.approval_failed", ticket_id=ticket_id)
        await broadcast(
            ticket_topic(ticket_id),
            AgentProgressMessage(
                payload=AgentProgressPayload(
                    stage="failed", detail="The agent is unavailable."
                )
            ),
        )

    await _then_whatever_waited(ticket_id, visibility)


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


async def decide_tool(
    ticket_id: str, *, approved: bool, arguments: dict[str, Any], publish: bool
) -> None:
    """Resume a run parked at the tool gate.

    What the agent writes afterwards goes where the reviewer said: a refund they
    approved is the customer's news, a lookup they ran is the team's.
    """
    lane = await parked_tool_lane(ticket_id)
    try:
        # Cleared first: the card is answered whatever the resumed run does.
        await forget_proposal(ticket_id)
        visibility = Visibility.PUBLIC if publish else Visibility.INTERNAL
        await _Run(
            TEAM,
            ticket_id,
            ToolDecisionPayload(
                conversation_id=ticket_id,
                approved=approved,
                arguments=arguments,
            ),
            TicketSink(ticket_id, visibility),
        ).handle()
    except Exception:
        logger.exception("support.tool_decision_failed", ticket_id=ticket_id)
        await broadcast(
            ticket_topic(ticket_id),
            AgentProgressMessage(
                payload=AgentProgressPayload(
                    stage="failed", detail="That tool call could not be finished."
                )
            ),
        )

    await _then_whatever_waited(ticket_id, lane)


async def start_tool_decision(
    ticket_id: str, *, approved: bool, arguments: dict[str, Any], publish: bool
) -> None:
    spawn(
        decide_tool(ticket_id, approved=approved, arguments=arguments, publish=publish)
    )
