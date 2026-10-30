from typing import Any, ClassVar, get_args

import structlog
from chanx.core.decorators import ws_handler
from chanx.core.topic import Topic
from chanx.messages.base import BaseMessage
from langchain_core.runnables import RunnableConfig

from assistant.agents import Audience, Context, Ticket, Turn
from assistant.agents.config import AgentConfig
from assistant.core.config import settings
from assistant.core.layers import LAYER_ALIAS
from assistant.graphs.states import SupportState
from assistant.graphs.states.base import ReplyRun, ToolRun
from assistant.graphs.support_graph import SupportGraph
from assistant.messages.support import (
    ApprovalDecisionMessage,
    RunEndedMessage,
    RunEndedPayload,
    RunFailedMessage,
    RunFailedPayload,
    RunRequestMessage,
    SupportEvent,
    ToolDecisionMessage,
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
            await self._run(self._turn(payload, context), payload.models)
        except Exception:
            await logger.aexception("support.run_failed", thread=self.topic)
            await self._fail()

    def _turn(self, payload: Any, context: Context) -> SupportState:
        """A new question on the thread, which is a new run.

        It starts clean. The only thing a turn inherits is what the thread is
        meant to remember: carry the whole blob and the last run's receipt and
        approval come with it, and the second question answers itself.
        """
        carried = payload.state or {}
        return SupportState(
            context=context,
            question=payload.question,
            messages_json=str(carried.get("messages_json") or ""),
        )

    def _continue(self, carried: dict[str, Any], **decision: Any) -> SupportState:
        """The same run, picked back up where it stopped.

        A whole state, not an update: the agent kept nothing, so the blob holds
        the thread's tool result, and a cancelled call must not report it as a
        success because the field defaulted.
        """
        return SupportState.model_validate({**carried, **decision})

    async def _run(self, state: SupportState, models: Any) -> None:
        """Drive the graph, then hand back what it ended with.

        Always, not only when it stopped for somebody: nothing is kept here, so
        a run that answered still has to say what the thread now remembers.
        """
        final = await self._consume(self._graph(models), state)
        await emitter_for(self)(
            RunEndedMessage(
                payload=RunEndedPayload(
                    thread_id=self.thread_id,
                    awaiting=self._awaiting(final),
                    state=SupportState.model_validate(final).model_dump(mode="json"),
                )
            ),
        )

    def _awaiting(self, final: dict[str, Any]) -> str:
        """What this run stopped for, read off the work rather than a flag.

        Only two things in the graph wait on a person, and each says so by
        leaving its own status pending.
        """
        if (final or {}).get("tool_run") == ToolRun.PENDING:
            return "tool_approval"
        if (final or {}).get("reply_run") == ReplyRun.PENDING:
            return "reply_approval"
        return ""

    @ws_handler(
        summary="Approve or reject a drafted reply",
        description="Carries on a run that stopped at the approval gate.",
        output_type=SupportEvent,
    )
    async def handle_approval_decision(self, message: ApprovalDecisionMessage) -> None:
        payload = message.payload
        await self._resumed_run(
            payload.state,
            payload.models,
            reply_run=ReplyRun.APPROVED if payload.approved else ReplyRun.REJECTED,
            **self._edit(payload.state, payload.content),
        )

    def _edit(self, carried: Any, content: str | None) -> dict[str, Any]:
        """A reviewer's rewrite, put where the answer already is.

        The whole answer, because a state is validated as a state: an extra
        key alongside it is dropped in silence, which is what sent the model's
        draft to a customer whose reviewer had rewritten it.
        """
        answer = (carried or {}).get("answer")
        if not content or not isinstance(answer, dict):
            return {}
        return {"answer": {**answer, "content": content}}

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
        extra: dict[str, Any] = {}
        if payload.arguments:
            # Corrections replace the proposal wholesale, so what the reviewer
            # saw is exactly what runs. Whether they changed anything is worth
            # carrying: the answer reads a corrected amount as an error unless
            # it is told the smaller number was somebody's decision.
            arguments = dict(payload.arguments)
            proposed = (payload.state or {}).get("arguments") or {}
            extra["arguments"] = arguments
            extra["corrected"] = arguments != proposed
        await self._resumed_run(
            payload.state,
            None,
            tool_run=ToolRun.APPROVED if payload.approved else ToolRun.CANCELLED,
            **extra,
        )

    async def _resumed_run(
        self,
        carried: dict[str, Any] | None,
        models: Any,
        **decision: Any,
    ) -> None:
        """Start a run from what the paused one left, plus the reviewer's answer."""
        if not carried:
            await logger.awarning("support.resume_without_state", thread=self.topic)
            await self._fail()
            return
        try:
            await self._run(self._continue(carried, **decision), models)
        except Exception:
            await logger.aexception("support.resume_failed", thread=self.topic)
            await self._fail()

    def _graph(self, models: Any) -> Any:
        """Built per run: the topology is fixed, but which model fills each
        purpose comes from the requesting user.

        Compiled without a checkpointer. A run that stops for a person ends,
        and the state it ended with comes back on the next request, so there
        is nothing for the graph to remember between them.
        """
        return SupportGraph(
            AgentConfig.from_slugs(models.model_dump() if models else None),
            emitter_for(self),
        ).compile()

    async def _consume(self, graph: Any, start: Any) -> dict[str, Any]:
        """Drained for its side effects, and for the state it ends with.

        Every node publishes its own events, including the pieces of a
        reasoning as it is written, so nothing is read out of the stream. The
        final state is read because a run that stopped for a person has to say
        so, and because that state is the whole of what resuming it needs.
        """
        config: RunnableConfig = {
            "configurable": {
                "thread_id": SupportGraph.thread(f"{self.audience}:{self.thread_id}")
            },
            "recursion_limit": settings.graph_recursion_limit,
        }

        # StateT is invariant in astream, so a declared `SupportState` cannot
        # satisfy it even though that is exactly what the graph accepts.
        stream: Any = graph.astream(start, config=config, stream_mode="values")
        final: dict[str, Any] = {}
        async for chunk in stream:
            if isinstance(chunk, dict):
                final = chunk
        return final

    async def _fail(self) -> None:
        """One event for both audiences. What to do about a dead run - hand the
        ticket to a person, or tell the team their question died - is the
        reader's to decide, and the backend decides it by which lane it is in."""
        await emitter_for(self)(
            RunFailedMessage(
                payload=RunFailedPayload(
                    thread_id=self.thread_id,
                    message="The agent could not finish that.",
                )
            ),
        )
