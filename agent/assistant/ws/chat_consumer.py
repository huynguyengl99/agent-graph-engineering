from typing import Any

import structlog
from chanx.core.decorators import channel, ws_handler
from chanx.fast_channels.websocket import AsyncJsonWebsocketConsumer
from chanx.messages.incoming import PingMessage
from chanx.messages.outgoing import PongMessage
from langchain_core.runnables import RunnableConfig

from assistant.agents.config import AgentConfig
from assistant.agents.deps import ChatContext, TicketContext
from assistant.graphs.chat_graph import build_chat_graph
from assistant.ws.chat_messages import (
    ChatCompleteMessage,
    ChatCompletePayload,
    ChatErrorMessage,
    ChatErrorPayload,
    ChatRequestMessage,
    ChatRequestPayload,
    ChatTokenMessage,
    ChatTokenPayload,
)

logger = structlog.get_logger(__name__)


@channel(
    name="chat",
    description="The support agent's own conversation with the assistant",
    tags=["agent", "chat"],
)
class ChatConsumer(AsyncJsonWebsocketConsumer):
    """Rep-facing, so nothing here is gated. Only a reply leaving for a ticket
    needs approval, and that happens on the tickets channel."""

    @ws_handler
    async def handle_ping(self, _message: PingMessage) -> PongMessage:
        return PongMessage()

    @ws_handler(
        summary="Ask the assistant",
        description=(
            "Runs the chat graph and forwards the answer as it is produced, "
            "then sends the finished text once."
        ),
        output_type=ChatTokenMessage | ChatCompleteMessage | ChatErrorMessage,
    )
    async def handle_chat_request(self, message: ChatRequestMessage) -> None:
        payload = message.payload
        try:
            await self._answer(payload)
        except Exception:
            logger.exception("chat.failed", conversation_id=payload.conversation_id)
            await self.send_message(
                ChatErrorMessage(
                    payload=ChatErrorPayload(
                        conversation_id=payload.conversation_id,
                        message="The assistant could not answer that.",
                    )
                )
            )

    async def _answer(self, payload: ChatRequestPayload) -> None:
        context = ChatContext(
            conversation_id=payload.conversation_id,
            history=[(turn.role, turn.content) for turn in payload.history],
            ticket=(
                TicketContext(
                    ticket_id=payload.ticket.ticket_id,
                    title=payload.ticket.title,
                    description=payload.ticket.description,
                )
                if payload.ticket
                else None
            ),
        )

        graph = build_chat_graph(AgentConfig.resolve())
        config: RunnableConfig = {
            "configurable": {"thread_id": payload.conversation_id}
        }

        answer = ""
        # "custom" carries the token deltas the node writes; "updates" carries
        # the node's return value, which is the text we persist.
        stream: Any = graph.astream(
            {"context": context, "question": payload.question},
            config=config,
            stream_mode=["updates", "custom"],
        )
        async for mode, chunk in stream:
            if mode == "custom":
                await self.send_message(
                    ChatTokenMessage(
                        payload=ChatTokenPayload(
                            conversation_id=payload.conversation_id,
                            delta=str(chunk["delta"]),
                        )
                    )
                )
            else:
                answer = self._answer_of(chunk) or answer

        await self.send_message(
            ChatCompleteMessage(
                payload=ChatCompletePayload(
                    conversation_id=payload.conversation_id, content=answer
                )
            )
        )

    def _answer_of(self, update: Any) -> str:
        if not isinstance(update, dict):
            return ""
        node = update.get("answer")
        return str(node.get("answer", "")) if isinstance(node, dict) else ""
