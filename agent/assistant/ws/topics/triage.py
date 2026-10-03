from typing import Any, ClassVar, get_args

import structlog
from chanx.core.decorators import ws_handler
from chanx.core.topic import Topic
from chanx.messages.base import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from assistant.agents import Audience, Context, Ticket, Turn
from assistant.agents.config import AgentConfig
from assistant.core.config import settings
from assistant.core.layers import LAYER_ALIAS
from assistant.graphs.states import SupportState
from assistant.graphs.support_graph import SupportGraph, build_support_graph
from assistant.messages.triage import (
    AnswerMessage,
    ApprovalDecisionMessage,
    ApprovalRequiredMessage,
    ApprovalRequiredPayload,
    ClassifiedMessage,
    DecidedMessage,
    ReplyBlockedMessage,
    ReplySentMessage,
    TriageErrorMessage,
    TriageErrorPayload,
    TriageRequestMessage,
)
from assistant.ws.feed import emitter_for
from assistant.ws.replay import Replays

logger = structlog.get_logger(__name__)


def _slugs(overrides: Any) -> dict[str, str | None] | None:
    """A user's model choices as `{purpose: slug}`, or None when unset."""
    return overrides.model_dump() if overrides is not None else None


TriageFeedEvent = (
    ClassifiedMessage
    | DecidedMessage
    | AnswerMessage
    | ApprovalRequiredMessage
    | ReplySentMessage
    | ReplyBlockedMessage
    | TriageErrorMessage
)


class TriageTopic(Replays, Topic[TriageFeedEvent]):
    """One ticket's triage run, addressed as `triage:<ticket_id>`.

    A topic rather than a channel so the run belongs to the ticket instead of to
    the socket that asked for it: a node can emit from inside a subgraph, a
    resume arrives on the connection that is already subscribed, and a second
    subscriber sees the same run.
    """

    pattern = "triage:{ticket_id}"
    channel_layer_alias = LAYER_ALIAS
    # The nodes broadcast, and an event with no handler is dropped with a log
    # line. Derived from the feed so the two cannot drift.
    passthrough_events: ClassVar[list[type[BaseMessage]]] = list(
        get_args(TriageFeedEvent)
    )

    async def authorize(self, **params: str) -> bool:
        """The socket is already authenticated: only the backend can reach this
        service, and the shared token is checked before the handshake."""
        return True

    @ws_handler(
        summary="Triage a ticket",
        description=(
            "Runs the triage graph. Emits the classification and the routing "
            "decision as they happen, then the proposed answer."
        ),
        output_type=(
            ClassifiedMessage
            | DecidedMessage
            | AnswerMessage
            | ApprovalRequiredMessage
            | ReplySentMessage
            | ReplyBlockedMessage
            | TriageErrorMessage
        ),
    )
    async def handle_triage_request(self, message: TriageRequestMessage) -> None:
        payload = message.payload
        context = Context(
            thread_id=self.params["ticket_id"],
            audience=Audience.CUSTOMER,
            ticket=Ticket(
                ticket_id=self.params["ticket_id"],
                title=payload.title,
                description=payload.description,
            ),
            history=[Turn(role="thread", content=line) for line in payload.history],
        )

        try:
            await self._run_graph(
                context, AgentConfig.from_slugs(_slugs(payload.models))
            )
        except Exception:
            logger.exception("assistant.run_failed", ticket_id=self.params["ticket_id"])
            await self._fail(self.params["ticket_id"])

    @ws_handler(
        summary="Approve or reject a drafted reply",
        description="Resumes a run paused at the approval interrupt.",
        output_type=ReplySentMessage | AnswerMessage | TriageErrorMessage,
    )
    async def handle_approval_decision(self, message: ApprovalDecisionMessage) -> None:
        payload = message.payload
        try:
            await self._drive(
                self.params["ticket_id"],
                Command(
                    resume={
                        "approved": payload.approved,
                        "content": payload.content,
                    }
                ),
                AgentConfig.from_slugs(_slugs(payload.models)),
            )
        except Exception:
            logger.exception(
                "assistant.resume_failed", ticket_id=self.params["ticket_id"]
            )
            await self._fail(self.params["ticket_id"])

    async def _fail(self, ticket_id: str) -> None:
        await self.broadcast(
            self.topic,
            TriageErrorMessage(
                payload=TriageErrorPayload(
                    ticket_id=ticket_id,
                    message="The triage agent could not complete this ticket.",
                )
            ),
        )

    async def _run_graph(
        self, context: Context, agent_config: AgentConfig | None = None
    ) -> None:
        # A whole state, not an update: the thread is the ticket, and every
        # field but it defaults, which is what clears the last run's receipt.
        await self._drive(
            context.ticket_id, SupportState(context=context), agent_config
        )

    async def _drive(
        self,
        ticket_id: str,
        payload: SupportState | Command[Any],
        agent_config: AgentConfig | None = None,
    ) -> None:
        """Stream one graph run, whether it is a fresh start or a resume.

        The thread id is the ticket, so a resume arriving on a different socket
        still finds the paused run.
        """
        config: RunnableConfig = {
            "configurable": {
                "thread_id": SupportGraph.thread(f"{Audience.CUSTOMER}:{ticket_id}")
            },
            "recursion_limit": settings.graph_recursion_limit,
        }

        # Built per run: the topology is fixed, but which model fills each
        # purpose comes from the requesting user.
        graph = build_support_graph(
            agent_config or AgentConfig.resolve(), emitter=emitter_for(self)
        )

        await self._stream(graph, payload, config, ticket_id)

    async def _stream(
        self, graph: Any, payload: Any, config: RunnableConfig, ticket_id: str
    ) -> None:
        """Drained for its side effects: the nodes emit their own events, and
        the park is the one thing no node is running to report."""
        # `stream_mode="updates"` yields one {node_name: update} dict per step.
        # StateT is invariant in astream, so a declared `TriageState | Command`
        # cannot satisfy it even though that is exactly what the graph accepts.
        async for step in graph.astream(
            payload,  # type: ignore[arg-type]
            config=config,
            stream_mode="updates",
        ):
            if (interrupted := step.get("__interrupt__")) is not None:
                await self._emit_interrupt(ticket_id, interrupted)

    async def _emit_interrupt(self, ticket_id: str, update: object) -> None:
        interrupts = update if isinstance(update, (list, tuple)) else [update]
        for item in interrupts:
            value = getattr(item, "value", item)
            if isinstance(value, dict) and value.get("kind") == "reply_approval":
                await self.broadcast(
                    self.topic,
                    ApprovalRequiredMessage(
                        payload=ApprovalRequiredPayload(
                            ticket_id=ticket_id,
                            draft=str(value.get("draft", "")),
                            findings=[str(f) for f in value.get("findings") or []],
                        )
                    ),
                )
