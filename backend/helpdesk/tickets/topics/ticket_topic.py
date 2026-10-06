from typing import Any

from channels.db import database_sync_to_async
from django.conf import settings

from chanx.core.decorators import ws_handler
from chanx.core.topic import Topic

from helpdesk.tickets.messages import (
    AgentProgressMessage,
    AgentProgressPayload,
    AgentWorkingMessage,
    AnswerStreamingMessage,
    ApprovalDecisionMessage,
    ApprovalRequiredMessage,
    AskAgentMessage,
    NewEventMessage,
    NewEventPayload,
    ReasoningStreamingMessage,
    SendMessageMessage,
    SetAgentMessage,
    TicketUpdatedMessage,
    ToolDecisionMessage,
    ToolProposalMessage,
    UpdateTicketMessage,
)
from helpdesk.tickets.messages.events import TicketEvent
from helpdesk.tickets.messages.events import TicketEvent as WireTicketEvent
from helpdesk.tickets.models import CommentEvent, Handling, Ticket, Visibility
from helpdesk.tickets.serializers.event import serialize_event
from helpdesk.tickets.services.handoff import hand_off, handling_of
from helpdesk.tickets.services.placeholders import UnfilledError, refuse_if_unfilled
from helpdesk.tickets.services.publish import publish
from helpdesk.tickets.services.status import set_priority, set_status, ticket_state

TicketFeedEvent = (
    NewEventMessage
    | AnswerStreamingMessage
    | AgentProgressMessage
    | AgentWorkingMessage
    | ApprovalRequiredMessage
    | ToolProposalMessage
    | TicketUpdatedMessage
    | ReasoningStreamingMessage
)


class TicketTopic(Topic[TicketFeedEvent]):
    """One ticket's activity, addressed as `ticket:<id>`.

    Everything published here may be read by the customer. The team's half is
    `ticket:<id>:team`, and staff subscribe to both - so the actions a reviewer
    takes arrive here, where both audiences already are.
    """

    pattern = "ticket:{ticket_id}"

    async def authorize(self, **params: str) -> bool:
        """Staff watch the queue; everyone else watches their own ticket. The
        REST list says the same, and a socket that said less was a way round
        it."""
        return bool(await self._may_watch(params["ticket_id"]))

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
        await publish(
            ticket_id,
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
            await publish(
                ticket_id,
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
        await publish(ticket_id, await ticket_state(ticket_id))

    async def _announce(self, ticket_id: str, event: TicketEvent | None) -> None:
        """`hand_off` answers with nothing when the ticket already stands where
        it is being moved to, and that is not an event."""
        if event is None:
            return
        await publish(ticket_id, NewEventMessage(payload=NewEventPayload(event=event)))

    # Everything published here is the customer's to read; what is not goes to
    # `ticket:<id>:team`, which only staff may join. See `services/publish.py`.
    passthrough_events = [
        NewEventMessage,
        AnswerStreamingMessage,
        ReasoningStreamingMessage,
        AgentWorkingMessage,
        TicketUpdatedMessage,
    ]

    @property
    def _staff(self) -> bool:
        user = self.scope.get("user")
        return bool(user is not None and getattr(user, "is_staff", False))

    @database_sync_to_async
    def _may_watch(self, ticket_id: str) -> bool:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            return False
        tickets = Ticket.objects.filter(id=ticket_id)
        if not user.is_staff:
            tickets = tickets.filter(created_by=user)
        return tickets.exists()

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
