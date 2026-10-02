from typing import Any

import structlog
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph, StateGraph

from assistant.agents.config import AgentConfig
from assistant.agents.factory import AgentFactory
from assistant.events import Emitter, silent
from assistant.tracing.nodes import Node, traced

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

    def build(self) -> StateGraph[Any, Any, Any, Any]:
        raise NotImplementedError

    def nodes(self) -> dict[str, Node]:
        raise NotImplementedError

    def add_nodes(self, graph: StateGraph[Any, Any, Any, Any]) -> None:
        for name, node in self.nodes().items():
            graph.add_node(name, traced(name, node))

    def compile(
        self, checkpointer: BaseCheckpointSaver[Any]
    ) -> CompiledStateGraph[Any, Any, Any, Any]:
        return self.build().compile(checkpointer=checkpointer)
