from typing import Any

from channels.db import database_sync_to_async
from django.conf import settings

from chanx.core.decorators import event_handler, ws_handler
from chanx.core.topic import Topic

from helpdesk.tickets.messages import (
    AgentProgressMessage,
    AgentProgressPayload,
    AgentWorkingMessage,
    ApprovalDecisionMessage,
    ApprovalRequiredMessage,
    AskAgentMessage,
    NewEventMessage,
    NewEventPayload,
    ReasoningDeltaMessage,
    SendMessageMessage,
    SetAgentMessage,
    TicketUpdatedMessage,
    ToolDecisionMessage,
    ToolProposalMessage,
    UpdateTicketMessage,
)
from helpdesk.tickets.messages.events import TicketEvent as WireTicketEvent
from helpdesk.tickets.models import CommentEvent, Handling, Ticket, Visibility
from helpdesk.tickets.serializers.event import serialize_event
from helpdesk.tickets.services.handoff import hand_off, handling_of
from helpdesk.tickets.services.placeholders import UnfilledError, refuse_if_unfilled
from helpdesk.tickets.services.status import set_priority, set_status, ticket_state

TicketFeedEvent = (
    NewEventMessage
    | AgentProgressMessage
    | AgentWorkingMessage
    | ApprovalRequiredMessage
    | ToolProposalMessage
    | TicketUpdatedMessage
    | ReasoningDeltaMessage
)


class TicketTopic(Topic[TicketFeedEvent]):
    """One ticket's activity, addressed as `ticket:<id>`.

    Customer-visible: everything here is the record of what was said on the
    ticket, which is why sending a reply goes through the approval gate.
    """

    pattern = "ticket:{ticket_id}"

    async def authorize(self, **params: str) -> bool:
        return bool(await self._ticket_exists(params["ticket_id"]))

    @ws_handler(
        summary="Post a comment",
        description="Appends a CommentEvent and hands the ticket to the agent.",
        output_type=NewEventMessage,
    )
    async def handle_send_message(self, message: SendMessageMessage) -> None:
        ticket_id = self.params["ticket_id"]
        event = await self._create_comment_event(
            ticket_id=ticket_id,
            content=message.payload.content,
            user=self.scope.get("user"),
            public=message.payload.public,
        )
        await self.broadcast(
            f"ticket:{ticket_id}",
            NewEventMessage(
                payload=NewEventPayload(event=await self._serialize(event))
            ),
        )

        user = self.scope.get("user")
        from_requester = await self._from_requester(ticket_id, user)

        # Answering the customer is taking the ticket: the agent stops replying
        # on its own once a person has.
        if event.visibility == Visibility.PUBLIC and not from_requester:
            await self._announce(
                ticket_id, await hand_off(ticket_id, Handling.WITH_STAFF, user=user)
            )
            return

        if not settings.AGENT_ON_COMMENT or not from_requester:
            return
        if event.visibility != Visibility.PUBLIC:
            return
        if await handling_of(ticket_id) != Handling.AGENT:
            return

        from helpdesk.tickets.services.support import start_run

        await start_run(
            ticket_id,
            visibility=Visibility.PUBLIC,
            user_id=user.pk if user is not None and user.is_authenticated else None,
        )

    @ws_handler(
        summary="Approve, edit, or reject the drafted reply",
        description="Resumes the paused run. Nothing reaches the customer until this arrives.",
        output_type=NewEventMessage | AgentProgressMessage,
    )
    async def handle_approval_decision(self, message: ApprovalDecisionMessage) -> None:
        from helpdesk.tickets.services.support import start_approval

        user = self.scope.get("user")
        await start_approval(
            self.params["ticket_id"],
            approved=message.payload.approved,
            content=message.payload.content,
            user_id=user.pk if user is not None and user.is_authenticated else None,
        )

    @ws_handler(
        summary="Ask the agent to work this ticket",
        description="Public answers the customer; internal drafts for the team only.",
        output_type=NewEventMessage | AgentProgressMessage,
    )
    async def handle_ask_agent(self, message: AskAgentMessage) -> None:

        from helpdesk.tickets.services.support import start_run

        ticket_id = self.params["ticket_id"]
        user = self.scope.get("user")
        user_id = user.pk if user is not None and user.is_authenticated else None
        question = message.payload.question.strip()

        # A question asked privately is asked of the agent, so it answers that
        # rather than drafting another reply to the customer.
        if question and not message.payload.public:
            event = await self._create_comment_event(
                ticket_id=ticket_id, content=question, user=user, public=False
            )
            await self.broadcast(
                f"ticket:{ticket_id}",
                NewEventMessage(
                    payload=NewEventPayload(event=await self._serialize(event))
                ),
            )
            await start_run(
                ticket_id,
                question=question,
                visibility=Visibility.INTERNAL,
                user_id=user_id,
            )
            return

        await start_run(
            ticket_id,
            visibility=(
                Visibility.PUBLIC if message.payload.public else Visibility.INTERNAL
            ),
            user_id=user_id,
        )

    @ws_handler(
        summary="Turn the agent on this ticket on or off",
        description="On, it answers new customer messages; off, the team does.",
        output_type=NewEventMessage | AgentProgressMessage,
    )
    async def handle_set_agent(self, message: SetAgentMessage) -> None:
        ticket_id = self.params["ticket_id"]
        user = self.scope.get("user")

        if said := message.payload.message.strip():
            try:
                refuse_if_unfilled(said)
            except UnfilledError as unfilled:
                await self.send_message(
                    AgentProgressMessage(
                        payload=AgentProgressPayload(
                            stage="failed",
                            detail=f"Fill in {', '.join(unfilled.names)} first.",
                        )
                    )
                )
                return
            await self._announce(
                ticket_id,
                await self._serialize(
                    await self._create_comment_event(
                        ticket_id=ticket_id, content=said, user=user, public=True
                    )
                ),
            )

        await self._announce(
            ticket_id,
            await hand_off(
                ticket_id,
                Handling.AGENT if message.payload.on else Handling.WITH_STAFF,
                user=user,
            ),
        )

    @ws_handler(
        summary="Approve, correct, or cancel a proposed tool call",
        description=(
            "Resumes the parked consult. Corrected arguments replace the "
            "proposed ones, so what the reviewer saw is what runs."
        ),
        output_type=NewEventMessage | AgentProgressMessage,
    )
    async def handle_tool_decision(self, message: ToolDecisionMessage) -> None:
        from helpdesk.tickets.services.support import start_tool_decision

        await start_tool_decision(
            self.params["ticket_id"],
            approved=message.payload.approved,
            arguments=message.payload.arguments,
            publish=message.payload.publish,
        )

    @ws_handler(
        summary="Set where the ticket stands",
        description="Staff only: the requester reports a problem, they do not grade it.",
        output_type=NewEventMessage | TicketUpdatedMessage,
    )
    async def handle_update_ticket(self, message: UpdateTicketMessage) -> None:
        if not self._staff:
            return

        ticket_id = self.params["ticket_id"]
        if priority := message.payload.priority:
            await set_priority(ticket_id, priority)
        if status := message.payload.status:
            await self._announce(
                ticket_id, await set_status(ticket_id, status, self.scope.get("user"))
            )
        await self.broadcast(f"ticket:{ticket_id}", await ticket_state(ticket_id))

    async def _announce(self, ticket_id: str, event: Any) -> None:
        if event is None:
            return
        await self.broadcast(
            f"ticket:{ticket_id}", NewEventMessage(payload=NewEventPayload(event=event))
        )

    # Relays: an event published to this topic goes to the clients allowed it.
    # One group carries the whole ticket, so the fan-out is where the customer's
    # half is separated from the team's - the REST list already does the same.
    @event_handler
    async def handle_new_event(self, event: NewEventMessage) -> NewEventMessage | None:
        wire = event.payload.event
        if wire.visibility != "public" and not self._staff:
            return None
        if self._staff:
            return event

        # Visible is not the same as readable: a handoff's reason and a tool
        # call's arguments are the team's, on an event the customer may see.
        hidden: dict[str, Any] = {}
        if wire.event_type == "handoff" and wire.reason:
            hidden = {"reason": ""}
        elif wire.event_type == "tool_call":
            hidden = {"arguments": {}, "result": "", "error": ""}
        if not hidden:
            return event
        return event.model_copy(
            update={
                "payload": event.payload.model_copy(
                    update={"event": wire.model_copy(update=hidden)}
                )
            }
        )

    @event_handler
    async def handle_progress(
        self, event: AgentProgressMessage
    ) -> AgentProgressMessage | None:
        """What the agent decided is the team's business."""
        return event if self._staff else None

    @event_handler
    async def handle_working(self, event: AgentWorkingMessage) -> AgentWorkingMessage:
        """That someone is dealing with your ticket is yours to know. It is only
        ever sent for a run answering the customer, and it carries nothing but
        the fact."""
        return event

    @event_handler
    async def handle_approval_required(
        self, event: ApprovalRequiredMessage
    ) -> ApprovalRequiredMessage | None:
        """A draft that has not been approved has not been sent."""
        return event if self._staff else None

    @event_handler
    async def handle_reasoning(
        self, event: ReasoningDeltaMessage
    ) -> ReasoningDeltaMessage | None:
        """The workings are the team's, even on a run the customer started."""
        return event if self._staff else None

    @event_handler
    async def handle_ticket_updated(
        self, event: TicketUpdatedMessage
    ) -> TicketUpdatedMessage:
        return event

    @event_handler
    async def handle_tool_proposal(
        self, event: ToolProposalMessage
    ) -> ToolProposalMessage | None:
        """A tool nobody has approved has not run."""
        return event if self._staff else None

    @property
    def _staff(self) -> bool:
        user = self.scope.get("user")
        return bool(user is not None and getattr(user, "is_staff", False))

    @database_sync_to_async
    def _ticket_exists(self, ticket_id: str) -> bool:
        return Ticket.objects.filter(id=ticket_id).exists()

    @database_sync_to_async
    def _create_comment_event(
        self, ticket_id: str, content: str, user: Any, public: bool
    ) -> CommentEvent:
        author = user if user is not None and user.is_authenticated else None
        ticket = Ticket.objects.get(id=ticket_id)
        # The requester cannot write a note to themselves; everyone else chooses,
        # and the default is internal.
        theirs = author is not None and author.pk == ticket.created_by_id
        return CommentEvent.objects.create(
            ticket_id=ticket_id,
            content=content,
            created_by=author,
            visibility=(Visibility.PUBLIC if theirs or public else Visibility.INTERNAL),
        )

    @database_sync_to_async
    def _from_requester(self, ticket_id: str, user: Any) -> bool:
        if user is None or not user.is_authenticated:
            return False
        return Ticket.objects.filter(id=ticket_id, created_by_id=user.pk).exists()

    @database_sync_to_async
    def _serialize(self, event: Any) -> WireTicketEvent:
        return serialize_event(event)
