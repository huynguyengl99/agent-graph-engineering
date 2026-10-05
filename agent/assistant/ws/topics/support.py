from typing import Any, ClassVar, get_args

import structlog
from chanx.core.decorators import ws_handler
from chanx.core.topic import Topic
from chanx.messages.base import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from assistant.agents import Audience, Context, Ticket, Turn
from assistant.agents.config import AgentConfig
from assistant.conversations import history
from assistant.core.config import settings
from assistant.core.layers import LAYER_ALIAS
from assistant.graphs.states import SupportState
from assistant.graphs.support_graph import SupportGraph, build_support_graph
from assistant.messages.support import (
    ApprovalDecisionMessage,
    ApprovalRequiredMessage,
    ApprovalRequiredPayload,
    ChatErrorMessage,
    ChatErrorPayload,
    RunRequestMessage,
    SupportEvent,
    ToolApprovalMessage,
    ToolApprovalPayload,
    ToolDecisionMessage,
    TriageErrorMessage,
    TriageErrorPayload,
)
from assistant.ws.feed import emitter_for
from assistant.ws.replay import Replays

logger = structlog.get_logger(__name__)


class SupportTopic(Replays, Topic[SupportEvent]):
    """One run, addressed as `support:<audience>:<thread_id>`.

    A topic rather than a channel so the run belongs to the thread instead of to
    the socket that asked for it: a node can emit from inside a subgraph, a
    resume arrives on a connection that is already subscribed, and a second
    subscriber sees the same run.

    The audience is in the address because a customer's run and the team's run
    about one ticket are two runs, with two checkpoints, that must not resume
    into each other.
    """

    pattern = "support:{audience}:{thread_id}"
    channel_layer_alias = LAYER_ALIAS
    # The nodes broadcast, and an event with no handler is dropped with a log
    # line. Derived from the feed so the two cannot drift.
    passthrough_events: ClassVar[list[type[BaseMessage]]] = list(get_args(SupportEvent))

    async def authorize(self, **params: str) -> bool:
        """The socket is already authenticated: only the backend can reach this
        service, and the shared token is checked before the handshake."""
        return True

    @property
    def audience(self) -> Audience:
        return Audience(self.params["audience"])

    @property
    def thread_id(self) -> str:
        return str(self.params["thread_id"])

    @ws_handler(
        summary="Work one message",
        description=(
            "Runs the support graph and forwards what it decides as it decides "
            "it, then the answer: drafted for the customer behind the approval "
            "gate, or streamed back to the team."
        ),
        output_type=SupportEvent,
    )
    async def handle_run_request(self, message: RunRequestMessage) -> None:
        payload = message.payload
        ticket = payload.ticket
        context = Context(
            thread_id=self.thread_id,
            audience=self.audience,
            ticket=(
                Ticket(
                    ticket_id=ticket.ticket_id,
                    title=ticket.title,
                    description=ticket.description,
                )
                if ticket
                else None
            ),
            history=[Turn(turn.role, turn.content) for turn in payload.history],
        )

        try:
            # Only used when this service has no history of its own yet.
            await history().seed(self.thread_id, context.history)
            await self._consume(
                self._graph(payload.models),
                # A whole state, not an update: the thread holds the last run's
                # tool result, and a cancelled call must not report it as a
                # success.
                SupportState(context=context, question=payload.question),
            )
        except Exception:
            logger.exception("support.run_failed", thread=self.topic)
            await self._fail()

    @ws_handler(
        summary="Approve or reject a drafted reply",
        description="Resumes a run paused at the approval interrupt.",
        output_type=SupportEvent,
    )
    async def handle_approval_decision(self, message: ApprovalDecisionMessage) -> None:
        payload = message.payload
        await self._resume(
            Command(resume={"approved": payload.approved, "content": payload.content}),
            payload.models,
        )

    @ws_handler(
        summary="Approve, correct, or cancel a proposed tool call",
        description=(
            "Resumes a run parked at the tool gate. Corrected arguments "
            "replace the proposed ones, so what the reviewer saw is what runs."
        ),
        output_type=SupportEvent,
    )
    async def handle_tool_decision(self, message: ToolDecisionMessage) -> None:
        payload = message.payload
        await self._resume(
            Command(
                resume={
                    "decision": "approve" if payload.approved else "cancel",
                    "arguments": payload.arguments,
                }
            ),
            None,
        )

    async def _resume(self, command: Command[Any], models: Any) -> None:
        try:
            await self._consume(self._graph(models), command)
        except Exception:
            logger.exception("support.resume_failed", thread=self.topic)
            await self._fail()

    def _graph(self, models: Any) -> Any:
        """Built per run: the topology is fixed, but which model fills each
        purpose comes from the requesting user."""
        return build_support_graph(
            AgentConfig.from_slugs(models.model_dump() if models else None),
            emitter=emitter_for(self),
        )

    async def _consume(self, graph: Any, start: Any) -> None:
        """Drained for its side effects.

        Every node publishes its own events, including the pieces of a
        reasoning as it is written, so nothing is read out of the stream here
        but the park - which is the one thing no node is running to report.
        """
        config: RunnableConfig = {
            "configurable": {
                "thread_id": SupportGraph.thread(f"{self.audience}:{self.thread_id}")
            },
            "recursion_limit": settings.graph_recursion_limit,
        }

        # StateT is invariant in astream, so a declared `SupportState | Command`
        # cannot satisfy it even though that is exactly what the graph accepts.
        stream: Any = graph.astream(start, config=config, stream_mode="updates")
        async for chunk in stream:
            if isinstance(chunk, dict) and "__interrupt__" in chunk:
                await self._parked(chunk["__interrupt__"])

    async def _parked(self, update: object) -> None:
        """Both gates interrupt; which one is in the value they carry."""
        interrupts = update if isinstance(update, list | tuple) else [update]
        for item in interrupts:
            value = getattr(item, "value", item)
            if not isinstance(value, dict):
                continue

            if value.get("kind") == "reply_approval":
                await self.broadcast(
                    self.topic,
                    ApprovalRequiredMessage(
                        payload=ApprovalRequiredPayload(
                            ticket_id=self.thread_id,
                            draft=str(value.get("draft", "")),
                            findings=[str(f) for f in value.get("findings") or []],
                        )
                    ),
                )
            elif value.get("kind") == "tool_approval":
                await self.broadcast(
                    self.topic,
                    ToolApprovalMessage(
                        payload=ToolApprovalPayload(
                            conversation_id=self.thread_id,
                            tool=str(value.get("tool", "")),
                            description=str(value.get("description", "")),
                            arguments=dict(value.get("arguments") or {}),
                            arguments_schema=dict(value.get("arguments_schema") or {}),
                            unknown_arguments=[
                                str(a) for a in value.get("unknown_arguments") or []
                            ],
                        )
                    ),
                )

    async def _fail(self) -> None:
        """Said in the audience's own words: the backend hands a failed
        customer run to a person, and tells the team its question died."""
        message = "The agent could not finish that."
        await self.broadcast(
            self.topic,
            TriageErrorMessage(
                payload=TriageErrorPayload(ticket_id=self.thread_id, message=message)
            )
            if self.audience is Audience.CUSTOMER
            else ChatErrorMessage(
                payload=ChatErrorPayload(
                    conversation_id=self.thread_id, message=message
                )
            ),
        )
