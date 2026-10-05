from typing import Any, cast

import structlog
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph, StateGraph

from assistant.agents.config import AgentConfig, ModelPurpose
from assistant.agents.factory import AgentFactory
from assistant.events import Emitter, silent
from assistant.messages.support import (
    ReasonedMessage,
    ReasonedPayload,
    ReasoningDeltaMessage,
    ReasoningDeltaPayload,
)
from assistant.tracing.nodes import Node, traced
from assistant.tracing.runs import TracedRun

logger = structlog.get_logger(__name__)


class BaseGraph:
    """What every graph in this service shares.

    Nodes are methods, so a graph carries its run's model config and its way of
    reporting without threading either through state. Tracing is applied here,
    once, rather than in any node body.
    """

    name: str

    def __init__(
        self, config: AgentConfig | None = None, emitter: Emitter = silent
    ) -> None:
        self.config = config or AgentConfig.resolve()
        self.factory = AgentFactory(self.config)
        self.emit = emitter
        logger.debug(
            "graph.built",
            graph=type(self).name,
            models={p.value: m.slug for p, m in self.config.models.items()},
        )

    @classmethod
    def thread(cls, key: str) -> str:
        """A checkpoint thread belongs to one graph.

        Keyed on the ticket alone, a consult about a ticket and its triage share
        a thread, and the next run fails validating the other's state.
        """
        return f"{cls.name}:{key}"

    async def reason(
        self,
        step: str,
        agent: Any,
        prompt: str,
        context: Any,
        history: Any = None,
    ) -> Any:
        """Run a step, reporting its reasoning as the model writes it.

        Structured output arrives in pieces, so every step that explains itself
        can be read while it decides rather than after.

        The deltas go out the way every other event does, as messages on the
        run's topic. They used to ride LangGraph's custom stream channel, which
        meant only the connection draining `astream` ever saw them: a second
        tab watching the same ticket got the finished reasoning and none of the
        writing. They are not replayable, because a reader who missed a
        half-written sentence has the finished one.
        """

        async def aloud(delta: str) -> None:
            await self.emit(
                ReasoningDeltaMessage(
                    payload=ReasoningDeltaPayload(
                        thread_id=context.thread_id, step=step, delta=delta
                    )
                ),
                replayable=False,
            )

        output = await agent.reason_aloud(prompt, context, history, on_delta=aloud)
        said = str(
            getattr(output, "reasoning", None) or getattr(output, "reason", None) or ""
        )
        if said:
            await self.emit(
                ReasonedMessage(
                    payload=ReasonedPayload(
                        thread_id=context.thread_id,
                        step=step,
                        content=said,
                        decision=type(output).__name__,
                        model=self.config.models[ModelPurpose.DECISION].slug,
                    )
                )
            )
        return output

    def build(self) -> StateGraph[Any, Any, Any, Any]:
        raise NotImplementedError

    def nodes(self) -> dict[str, Node]:
        raise NotImplementedError

    def add_nodes(self, graph: StateGraph[Any, Any, Any, Any]) -> None:
        for name, node in self.nodes().items():
            graph.add_node(name, traced(name, node))

    def subgraph(self) -> CompiledStateGraph[Any, Any, Any, Any]:
        """Compiled to be added to a parent as a node.

        No checkpointer of its own - it shares the parent's, which is what lets
        a resume reach an interrupt one level down - and no run span, because
        the run it belongs to is the parent's.
        """
        return self.build().compile()

    def compile(
        self, checkpointer: BaseCheckpointSaver[Any] | None = None
    ) -> CompiledStateGraph[Any, Any, Any, Any]:
        compiled = self.build().compile(checkpointer=checkpointer)
        return cast(
            CompiledStateGraph[Any, Any, Any, Any], TracedRun(self.name, compiled)
        )
