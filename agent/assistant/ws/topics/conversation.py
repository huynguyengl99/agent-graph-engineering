from typing import Any

import structlog
from chanx.core.decorators import ws_handler
from chanx.core.topic import Topic
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from assistant.agents.config import AgentConfig
from assistant.agents.deps import ChatContext, TicketContext
from assistant.core.config import settings
from assistant.core.layers import LAYER_ALIAS
from assistant.graphs.chat_graph import build_chat_graph
from assistant.graphs.states import ChatState
from assistant.messages.chat import (
    ChatCompleteMessage,
    ChatCompletePayload,
    ChatErrorMessage,
    ChatErrorPayload,
    ChatRequestMessage,
    ChatRequestPayload,
    ChatTokenMessage,
    ChatTokenPayload,
    ToolApprovalMessage,
    ToolApprovalPayload,
    ToolDecisionMessage,
)
from assistant.tracing import run_span

logger = structlog.get_logger(__name__)


# The thread is the conversation, so a second question resumes a thread still
# holding the last turn's tool result. `answer` prefers a result over a
# cancellation, so without this a cancelled call is reported as the previous
# call's success - which is the worst possible way to get that wrong.
FRESH_TURN: ChatState = {
    "route": None,  # type: ignore[typeddict-item]
    "answer": "",
    "kb_query": "",
    "kb_snippets": [],
    "request": "",
    "tool": "",
    "arguments": {},
    "unknown_arguments": [],
    "approved": False,
    "cancelled": False,
    "result": "",
    "tool_error": "",
}


ChatFeedEvent = (
    ChatTokenMessage | ChatCompleteMessage | ToolApprovalMessage | ChatErrorMessage
)


class ConversationTopic(Topic[ChatFeedEvent]):
    """A rep's thread with the assistant, addressed as `conversation:<id>`.

    Nothing here reaches a customer. A reply only becomes irreversible when it
    leaves for a ticket, which is the tickets topic and its own gate.
    """

    pattern = "conversation:{conversation_id}"
    channel_layer_alias = LAYER_ALIAS

    async def authorize(self, **params: str) -> bool:
        return True

    """Rep-facing, so nothing here is gated. Only a reply leaving for a ticket
    needs approval, and that happens on the tickets channel."""

    @ws_handler(
        summary="Ask the assistant",
        description=(
            "Runs the chat graph and forwards the answer as it is produced, "
            "then sends the finished text once."
        ),
        output_type=(
            ChatTokenMessage
            | ChatCompleteMessage
            | ToolApprovalMessage
            | ChatErrorMessage
        ),
    )
    async def handle_chat_request(self, message: ChatRequestMessage) -> None:
        payload = message.payload
        try:
            await self._answer(payload)
        except Exception:
            logger.exception(
                "chat.failed", conversation_id=self.params["conversation_id"]
            )
            await self._fail(self.params["conversation_id"])

    async def _answer(self, payload: ChatRequestPayload) -> None:
        context = ChatContext(
            conversation_id=self.params["conversation_id"],
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

        graph = build_chat_graph(
            AgentConfig.from_slugs(
                payload.models.model_dump() if payload.models else None
            )
        )

        with run_span("chat", self.params["conversation_id"]):
            start: ChatState = {
                "context": context,
                "question": payload.question,
                **FRESH_TURN,
            }
            await self._consume(graph, start, self.params["conversation_id"])

    @ws_handler(
        summary="Approve, correct, or cancel a proposed tool call",
        description=(
            "Resumes a run parked at the tool gate. Corrected arguments "
            "replace the proposed ones, so what the reviewer saw is what runs."
        ),
        output_type=ChatTokenMessage | ChatCompleteMessage | ChatErrorMessage,
    )
    async def handle_tool_decision(self, message: ToolDecisionMessage) -> None:
        payload = message.payload
        graph = build_chat_graph(AgentConfig.resolve())
        resume = {
            "decision": "approve" if payload.approved else "cancel",
            "arguments": payload.arguments,
        }
        try:
            with run_span("chat", self.params["conversation_id"]):
                await self._consume(
                    graph, Command(resume=resume), self.params["conversation_id"]
                )
        except Exception:
            logger.exception(
                "chat.resume_failed", conversation_id=self.params["conversation_id"]
            )
            await self._fail(self.params["conversation_id"])

    async def _fail(self, conversation_id: str) -> None:
        await self.send_message(
            ChatErrorMessage(
                payload=ChatErrorPayload(
                    conversation_id=conversation_id,
                    message="The assistant could not finish that.",
                )
            )
        )

    async def _consume(self, graph: Any, start: Any, conversation_id: str) -> None:
        config: RunnableConfig = {
            "configurable": {"thread_id": conversation_id},
            "recursion_limit": settings.graph_recursion_limit,
        }
        answer = ""
        parked = False
        stream: Any = graph.astream(
            start,
            config=config,
            stream_mode=["updates", "custom"],
        )
        async for mode, chunk in stream:
            if mode == "custom":
                await self.send_message(
                    ChatTokenMessage(
                        payload=ChatTokenPayload(
                            conversation_id=conversation_id,
                            delta=str(chunk["delta"]),
                        )
                    )
                )
                continue

            if isinstance(chunk, dict) and "__interrupt__" in chunk:
                parked = await self._emit_tool_approval(
                    conversation_id, chunk["__interrupt__"]
                )
                continue
            answer = self._answer_of(chunk) or answer

        if parked:
            # The run is waiting on a person; there is no answer to complete.
            return

        await self.send_message(
            ChatCompleteMessage(
                payload=ChatCompletePayload(
                    conversation_id=conversation_id, content=answer
                )
            )
        )

    async def _emit_tool_approval(self, conversation_id: str, update: Any) -> bool:
        interrupts = update if isinstance(update, list | tuple) else [update]
        for item in interrupts:
            value = getattr(item, "value", item)
            if isinstance(value, dict) and value.get("kind") == "tool_approval":
                await self.send_message(
                    ToolApprovalMessage(
                        payload=ToolApprovalPayload(
                            conversation_id=conversation_id,
                            tool=str(value.get("tool", "")),
                            description=str(value.get("description", "")),
                            arguments=dict(value.get("arguments") or {}),
                            arguments_schema=dict(value.get("arguments_schema") or {}),
                            unknown_arguments=[
                                str(name)
                                for name in value.get("unknown_arguments") or []
                            ],
                        )
                    )
                )
                return True
        return False

    def _answer_of(self, update: Any) -> str:
        if not isinstance(update, dict):
            return ""
        node = update.get("answer")
        return str(node.get("answer", "")) if isinstance(node, dict) else ""
