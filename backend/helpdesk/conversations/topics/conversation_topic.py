from uuid import UUID

from channels.db import database_sync_to_async

from chanx.core.decorators import event_handler, ws_handler
from chanx.core.topic import Topic

from helpdesk.conversations.messages import (
    AskMessage,
    AssistantDoneMessage,
    ChatErrorMessage,
    ChatMessageMessage,
    DraftToTicketMessage,
    TokenMessage,
    ToolApprovalMessage,
    ToolDecisionMessage,
)
from helpdesk.conversations.models import Conversation

ChatFeedEvent = (
    ChatMessageMessage
    | TokenMessage
    | AssistantDoneMessage
    | ToolApprovalMessage
    | ChatErrorMessage
)


class ConversationTopic(Topic[ChatFeedEvent]):
    """A rep's thread with the assistant, addressed as `conversation:<id>`.

    Internal: nothing said here reaches a customer, which is why the assistant
    answers freely and only `draft_to_ticket` is gated.
    """

    pattern = "conversation:{conversation_id}"

    async def authorize(self, **params: str) -> bool:
        # A conversation is the rep's own working space, never shared.
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            return False
        return bool(await self._owns(params["conversation_id"], user.pk))

    @ws_handler(
        summary="Ask the assistant",
        description="Streams the answer back token by token, then persists it.",
        output_type=(
            ChatMessageMessage
            | TokenMessage
            | AssistantDoneMessage
            | ToolApprovalMessage
        ),
    )
    async def handle_ask(self, message: AskMessage) -> None:
        from helpdesk.conversations.services.chat import start_turn

        user = self.scope.get("user")
        await start_turn(
            self.params["conversation_id"],
            message.payload.content,
            user.pk if user is not None and user.is_authenticated else None,
        )

    @ws_handler(
        summary="Send a drafted reply to a ticket",
        description=(
            "The one path out of the conversation. It resumes that ticket's "
            "run at its approval gate, so the customer-facing send is "
            "still gated."
        ),
        output_type=ChatErrorMessage,
    )
    async def handle_draft_to_ticket(self, message: DraftToTicketMessage) -> None:
        from helpdesk.tickets.services.support import start_approval

        payload = message.payload
        user = self.scope.get("user")
        await start_approval(
            payload.ticket_id,
            approved=True,
            content=payload.content,
            user_id=user.pk if user is not None and user.is_authenticated else None,
        )

    @ws_handler(
        summary="Approve, correct, or cancel a proposed tool call",
        description=(
            "Resumes the turn parked at the agent's tool gate. Corrections "
            "replace the proposed arguments, so what the reviewer saw is what "
            "runs."
        ),
        output_type=TokenMessage | AssistantDoneMessage | ChatErrorMessage,
    )
    async def handle_tool_decision(self, message: ToolDecisionMessage) -> None:
        from helpdesk.conversations.services.chat import start_tool_decision

        payload = message.payload
        await start_tool_decision(
            self.params["conversation_id"],
            approved=payload.approved,
            arguments=payload.arguments,
        )

    @event_handler
    async def handle_tool_approval(
        self, event: ToolApprovalMessage
    ) -> ToolApprovalMessage:
        return event

    @event_handler
    async def handle_chat_message(
        self, event: ChatMessageMessage
    ) -> ChatMessageMessage:
        return event

    @event_handler
    async def handle_token(self, event: TokenMessage) -> TokenMessage:
        return event

    @event_handler
    async def handle_done(self, event: AssistantDoneMessage) -> AssistantDoneMessage:
        return event

    @event_handler
    async def handle_error(self, event: ChatErrorMessage) -> ChatErrorMessage:
        return event

    @database_sync_to_async
    def _owns(self, conversation_id: str, user_pk: UUID) -> bool:
        return Conversation.objects.filter(id=conversation_id, owner=user_pk).exists()
